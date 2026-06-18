type WindowLayout = {
  width: number;
  height: number;
  resizable: boolean;
  restore?: boolean;
};

async function applyWindowLayout(layout: WindowLayout) {
  try {
    const { getCurrentWindow } = await import('@tauri-apps/api/window');
    const { LogicalSize } = await import('@tauri-apps/api/dpi');
    const appWindow = getCurrentWindow();
    if (layout.restore) {
      await appWindow.setFullscreen(false);
      await appWindow.unmaximize();
    }
    await appWindow.setSize(new LogicalSize(layout.width, layout.height));
    await appWindow.setResizable(layout.resizable);
    await appWindow.center();
  } catch {
    // Browser and Playwright environments do not provide a Tauri window.
  }
}

export function applyLauncherWindowLayout() {
  return applyWindowLayout({ width: 580, height: 580, resizable: false, restore: true });
}

export function applyMainWindowLayout() {
  return applyWindowLayout({ width: 1280, height: 800, resizable: true });
}

export async function safeConfirm(message: string): Promise<boolean> {
  try {
    const { confirm } = await import('@tauri-apps/plugin-dialog');
    return await confirm(message);
  } catch {
    return window.confirm(message);
  }
}
