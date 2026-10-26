"""Browse local folder names without uploading or scanning project files."""
from pathlib import Path


def list_project_folders(path=None):
    if path is not None and not isinstance(path, str):
        raise ValueError('文件夹路径无效。')
    try:
        folder = Path(path).expanduser().resolve() if path else Path.home().resolve()
        if not folder.is_dir():
            raise ValueError('文件夹不存在或已不可用，请重新选择。')
        children = []
        for entry in folder.iterdir():
            if entry.name.startswith('.'):
                continue
            try:
                if entry.is_dir():
                    children.append(dict(name=entry.name, path=str(entry)))
            except OSError:
                continue
        children.sort(key=lambda item: item['name'].casefold())
    except (PermissionError, OSError):
        raise ValueError('无法浏览这个文件夹，请选择有访问权限的文件夹。') from None
    shortcuts = [dict(name='个人文件夹', path=str(Path.home()))]
    desktop = Path.home() / 'Desktop'
    if desktop.is_dir():
        shortcuts.append(dict(name='桌面', path=str(desktop)))
    return dict(path=str(folder), name=folder.name or str(folder),
                parent=str(folder.parent) if folder.parent != folder else None,
                folders=children, shortcuts=shortcuts)
