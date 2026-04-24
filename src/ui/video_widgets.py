from pathlib import Path

from PySide6.QtCore import QUrl, Qt, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSlider, QSizePolicy, QStyle, QStyleOptionSlider, QVBoxLayout, QWidget

from logs.logger import log_ui


class ClickableSlider(QSlider):
    clicked_value = Signal(int)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            option = QStyleOptionSlider()
            self.initStyleOption(option)
            groove = self.style().subControlRect(
                QStyle.ComplexControl.CC_Slider,
                option,
                QStyle.SubControl.SC_SliderGroove,
                self,
            )

            if self.orientation() == Qt.Orientation.Horizontal:
                length = max(1, groove.width())
                position = max(0, min(event.pos().x() - groove.x(), length))
            else:
                length = max(1, groove.height())
                position = max(0, min(event.pos().y() - groove.y(), length))

            value = QStyle.sliderValueFromPosition(
                self.minimum(),
                self.maximum(),
                position,
                length,
                option.upsideDown,
            )
            self.setValue(value)
            self.clicked_value.emit(value)
            event.accept()

        super().mousePressEvent(event)


class VideoPlayerWidget(QWidget):
    def __init__(self, compact: bool = False):
        super().__init__()
        self.compact = compact
        self.media_path = Path()
        self.pending_play = False
        self.pending_position = None
        self.wide_callback = None
        self.fullscreen_callback = None
        self.mode_provider = None
        self.player = QMediaPlayer(self)
        self.audio = None
        if compact:
            self.player.setAudioOutput(None)
        else:
            self.audio = QAudioOutput(self)
            self.player.setAudioOutput(self.audio)

        self.video = QVideoWidget()
        self.video.setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatio)
        self.player.setVideoOutput(self.video)
        if compact:
            self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            self.video.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self.play_button = QPushButton(">")
        self.play_button.clicked.connect(self.toggle_play)
        self.back_button = QPushButton("-5")
        self.back_button.clicked.connect(lambda: self.seek_relative(-5000))
        self.forward_button = QPushButton("+5")
        self.forward_button.clicked.connect(lambda: self.seek_relative(5000))
        self.position = ClickableSlider(Qt.Orientation.Horizontal)
        self.position.setRange(0, 0)
        self.position.sliderMoved.connect(self.player.setPosition)
        self.position.clicked_value.connect(self.player.setPosition)
        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setObjectName("MutedLabel")
        self.time_label.setFixedWidth(92)
        self.volume = ClickableSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(100)
        self.volume.setFixedWidth(68)
        self.volume.valueChanged.connect(self.set_volume)
        self.wide_button = QPushButton("W")
        self.wide_button.clicked.connect(self.request_wide)
        self.fullscreen_button = QPushButton("F")
        self.fullscreen_button.clicked.connect(self.request_fullscreen)

        for button in [
            self.play_button,
            self.back_button,
            self.forward_button,
            self.wide_button,
            self.fullscreen_button,
        ]:
            button.setObjectName("TransportButton")
            button.setFixedSize(30, 30)
            button.setCursor(Qt.CursorShape.PointingHandCursor)

        self.position.setFixedHeight(30)
        self.volume.setFixedHeight(30)
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.time_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        controls = QHBoxLayout()
        controls.setContentsMargins(10, 5, 10, 5)
        controls.setSpacing(10)
        controls.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        controls.addWidget(self.play_button)
        controls.addWidget(self.back_button)
        controls.addWidget(self.forward_button)
        controls.addWidget(self.position, 1)
        controls.addWidget(self.time_label)
        controls.addWidget(self.volume)
        controls.addWidget(self.wide_button)
        controls.addWidget(self.fullscreen_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(8)
        layout.addWidget(self.video, 1)
        if not compact:
            layout.addLayout(controls)

        self.player.positionChanged.connect(self.position.setValue)
        self.player.positionChanged.connect(self.update_time_label)
        self.player.durationChanged.connect(self.update_duration)
        self.player.playbackStateChanged.connect(self.update_button)
        self.player.mediaStatusChanged.connect(self.handle_media_status)
        self.player.errorOccurred.connect(self.log_error)
        if self.audio:
            self.audio.mutedChanged.connect(self.sync_audio_controls)
            self.audio.volumeChanged.connect(self.sync_audio_controls)
        self.update_time_label(0)
        self.sync_audio_controls()
        self.update_view_buttons()

    def load(self, media_path: Path):
        self.media_path = media_path
        self.pending_play = False
        self.pending_position = None
        self.player.stop()
        self.player.setSource(QUrl.fromLocalFile(str(media_path)))
        if self.compact:
            self.disable_audio_track()

    def play(self):
        if self.media_path:
            self.pending_play = True
            self.player.play()

    def pause(self):
        self.player.pause()

    def stop(self):
        self.pending_play = False
        self.player.stop()

    def position_value(self) -> int:
        return self.player.position()

    def duration_value(self) -> int:
        return self.player.duration()

    def set_position(self, position: int):
        target = max(0, position)
        self.pending_position = target
        if self.player.duration() > 0:
            self.apply_pending_position()

    def is_playing(self) -> bool:
        return self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    def has_media(self) -> bool:
        return bool(self.media_path)

    def toggle_play(self):
        if self.is_playing():
            self.pause()
        else:
            self.play()

    def update_button(self, state):
        self.play_button.setText("||" if state == QMediaPlayer.PlaybackState.PlayingState else ">")

    def update_duration(self, duration: int):
        self.position.setRange(0, max(0, duration))
        self.apply_pending_position()
        self.update_time_label(self.player.position())

    def handle_media_status(self, status):
        if self.compact:
            self.disable_audio_track()
        if status in {
            QMediaPlayer.MediaStatus.LoadedMedia,
            QMediaPlayer.MediaStatus.BufferedMedia,
            QMediaPlayer.MediaStatus.BufferingMedia,
        }:
            self.apply_pending_position()
        if self.pending_play and status in {
            QMediaPlayer.MediaStatus.LoadedMedia,
            QMediaPlayer.MediaStatus.BufferedMedia,
            QMediaPlayer.MediaStatus.BufferingMedia,
        }:
            self.player.play()
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.player.setPosition(0)
            self.player.play()

    def disable_audio_track(self):
        try:
            self.player.setActiveAudioTrack(-1)
        except Exception:
            pass

    def apply_pending_position(self):
        if self.pending_position is None:
            return
        duration = self.player.duration()
        if duration <= 0:
            return
        target = min(self.pending_position, max(0, duration - 1))
        self.player.setPosition(target)
        self.pending_position = None

    def log_error(self, error, error_text):
        if error:
            log_ui("ERROR", "Qt video playback failed", path=str(self.media_path), error=str(error_text))

    def seek_relative(self, delta_ms: int):
        self.set_position(self.player.position() + delta_ms)

    def set_volume(self, value: int):
        if not self.audio:
            return
        self.audio.setMuted(value == 0)
        self.audio.setVolume(max(0.0, min(1.0, value / 100.0)))
        self.sync_audio_controls()

    def sync_audio_controls(self, *args):
        if not self.audio:
            self.volume.hide()
            return
        value = int(round(self.audio.volume() * 100))
        self.volume.blockSignals(True)
        self.volume.setValue(value)
        self.volume.blockSignals(False)

    def update_time_label(self, position: int):
        self.time_label.setText(f"{self._format_time(position)} / {self._format_time(self.player.duration())}")

    def _format_time(self, ms: int) -> str:
        total_seconds = max(0, ms // 1000)
        minutes, seconds = divmod(total_seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"

    def set_view_callbacks(self, wide_callback=None, fullscreen_callback=None, mode_provider=None):
        self.wide_callback = wide_callback
        self.fullscreen_callback = fullscreen_callback
        self.mode_provider = mode_provider
        self.update_view_buttons()

    def request_wide(self):
        if self.wide_callback:
            self.wide_callback()

    def request_fullscreen(self):
        if self.fullscreen_callback:
            self.fullscreen_callback()

    def update_view_buttons(self):
        mode = self.mode_provider() if self.mode_provider else "normal"
        self.wide_button.setVisible(not self.compact and mode != "fullscreen")
        self.fullscreen_button.setVisible(not self.compact)
        self.wide_button.setText("X" if mode == "wide" else "W")
        self.fullscreen_button.setText("X" if mode == "fullscreen" else "F")
