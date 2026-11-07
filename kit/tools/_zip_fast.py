import os
import zipfile

root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, 'dist'))
app = 'PPSA09010'
out = os.path.join(root, app + '.zip')
if os.path.exists(out):
    os.remove(out)
with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
    for folder, _dirs, files in os.walk(os.path.join(root, app)):
        for name in sorted(files):
            path = os.path.join(folder, name)
            arc = os.path.relpath(path, root).replace('\\', '/')
            archive.write(path, arc)
print('wrote', out, os.path.getsize(out))
