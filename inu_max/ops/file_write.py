"""Stage related resource files before replacing any destination."""
import os
import shutil
import tempfile


def write_batch(payloads):
    normalized = [os.path.normcase(os.path.abspath(p)) for p in payloads]
    if len(set(normalized)) != len(normalized):
        raise ValueError('Export destinations overlap')
    staged, backups, replaced = {}, {}, []
    retained = set()
    try:
        for path, data in payloads.items():
            folder = os.path.dirname(os.path.abspath(path))
            fd, temporary = tempfile.mkstemp(dir=folder, prefix='.inu_write_')
            staged[path] = temporary
            with os.fdopen(fd, 'wb') as stream:
                stream.write(data)
            if os.path.exists(path):
                fd, backup = tempfile.mkstemp(dir=folder, prefix='.inu_backup_')
                os.close(fd)
                backups[path] = backup
                shutil.copy2(path, backup)
        for path, temporary in staged.items():
            os.replace(temporary, path)
            replaced.append(path)
    except Exception:
        failures = []
        for path in reversed(replaced):
            try:
                if path in backups:
                    os.replace(backups[path], path)
                else:
                    os.unlink(path)
            except OSError as error:
                if path in backups:
                    retained.add(backups[path])
                failures.append('%s: %s; backup: %s' % (path, error, backups.get(path, 'none')))
        if failures:
            raise OSError('Export failed and rollback needs recovery: ' + '; '.join(failures))
        raise
    finally:
        for temporary in list(staged.values()) + list(backups.values()):
            if temporary not in retained and os.path.exists(temporary):
                os.unlink(temporary)
