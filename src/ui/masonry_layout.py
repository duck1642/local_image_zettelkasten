from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtWidgets import QLayout, QLayoutItem

class MasonryLayout(QLayout):
    def __init__(self, parent=None, spacing=10, column_width=210):
        super().__init__(parent)
        self.setSpacing(spacing)
        self.column_width = column_width
        self.items = []

    def __del__(self):
        item = self.takeAt(0)
        while item:
            item = self.takeAt(0)

    def addItem(self, item):
        self.items.append(item)

    def count(self):
        return len(self.items)

    def itemAt(self, index):
        if 0 <= index < len(self.items):
            return self.items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self.items):
            return self.items.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientations(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), apply_geometry=False)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, apply_geometry=True)

    def sizeHint(self):
        return QSize(self.column_width, 500)

    def minimumSize(self):
        return QSize(self.column_width, 100)

    def _do_layout(self, rect, apply_geometry=False):
        """
        The Pinterest Logic: Place each item in the column with the minimum current height.
        """
        spacing = self.spacing()
        effective_width = rect.width()
        
        # Calculate how many columns fit based on column_width and spacing
        num_columns = max(1, (effective_width + spacing) // (self.column_width + spacing))
        
        # Track the current height of each column
        col_heights = [rect.y()] * num_columns
        
        for item in self.items:
            # 1. Find the column with the minimum height
            min_col_idx = col_heights.index(min(col_heights))
            
            # 2. Calculate position
            x = rect.x() + min_col_idx * (self.column_width + spacing)
            y = col_heights[min_col_idx]
            
            # 3. Get item height
            # We respect heightForWidth if available, otherwise fallback to sizeHint
            item_height = item.heightForWidth(self.column_width)
            if item_height <= 0:
                item_height = item.sizeHint().height()
            
            # 4. Apply geometry
            if apply_geometry:
                item.setGeometry(QRect(QPoint(x, y), QSize(self.column_width, item_height)))
            
            # 5. Update column height for the next item
            col_heights[min_col_idx] = y + item_height + spacing

        # Return total required height
        return max(col_heights) - rect.y() if col_heights else 0
