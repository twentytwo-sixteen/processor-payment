import ast
import tomllib
from pathlib import Path


def test_services_expose_only_execute_and_do_not_import_orm_or_transport() -> None:
    root = Path('src/payment_processor/apps')
    for path in root.rglob('*service.py'):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name.endswith('Service'):
                public = [
                    item.name
                    for item in node.body
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and not item.name.startswith('_')
                ]
                assert public == ['execute'], (path, public)
            if isinstance(node, ast.ImportFrom):
                module = node.module or ''
                assert not any(
                    value in module for value in ('.models', '.contracts', '.rest_api', 'fastapi', 'faststream')
                )


def test_all_declared_dependencies_are_pinned() -> None:
    config = tomllib.loads(Path('pyproject.toml').read_text())
    requirements = (
        config['project']['dependencies'] + config['dependency-groups']['dev'] + config['build-system']['requires']
    )
    assert all('==' in value and not any(symbol in value for symbol in ('>', '<', '~', '*')) for value in requirements)
