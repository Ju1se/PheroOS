"""Complete source identity for local inspection execution and replay."""
from hashlib import sha256
from pathlib import Path


def source_identity():
    """Cover all installed or editable source roots, using portable module paths."""
    import pheroos_interaction
    from pheroos_interaction import runner

    identity = {}
    for package in (pheroos_interaction, runner):
        for directory in package.__path__:
            base = Path(directory)
            for path in sorted(base.rglob('*.py')):
                key = package.__name__.replace('.', '/') + '/' + path.relative_to(base).as_posix()
                value = sha256(path.read_bytes()).hexdigest()
                if key in identity and identity[key] != value:
                    raise RuntimeError('conflicting source identity')
                identity[key] = value
    return dict(sorted(identity.items()))
