import importlib
import os
import sys
import textwrap

import pytest

from liberator import Liberator
from liberator.core import DefinitionVisitor


def _write_module(tmp_path, relpath, text):
    fpath = tmp_path / relpath
    fpath.parent.mkdir(parents=True, exist_ok=True)
    fpath.write_text(textwrap.dedent(text))
    return fpath


def _import_temp_module(tmp_path, modname):
    sys.path.insert(0, str(tmp_path))
    try:
        module = importlib.import_module(modname)
    finally:
        sys.path.pop(0)
    return module


class _TempSysPath:
    def __init__(self, path):
        self.path = str(path)

    def __enter__(self):
        sys.path.insert(0, self.path)

    def __exit__(self, ex_type, ex, tb):
        sys.path.pop(0)


def _cleanup_module(modname):
    sys.modules.pop(modname, None)


def test_import_dotted_binds_root_and_expands(tmp_path):
    _write_module(tmp_path, 'pkg/__init__.py', '')
    _write_module(tmp_path, 'pkg/submod.py', 'def foo(x):\n    return x + 1\n')
    _write_module(
        tmp_path,
        'usermod_a.py',
        '''
        import pkg.submod
        def bar(x):
            return pkg.submod.foo(x)
        ''',
    )

    usermod = _import_temp_module(tmp_path, 'usermod_a')
    try:
        with _TempSysPath(tmp_path):
            lib = Liberator()
            lib.add_dynamic(usermod.bar, eager=True)
            lib.expand(['pkg'])
            text = lib.current_sourcecode()
            ns = {}
            exec(text, ns, ns)
            assert ns['bar'](1) == 2
    finally:
        _cleanup_module('usermod_a')
        _cleanup_module('pkg')
        _cleanup_module('pkg.submod')


def test_import_dotted_alias_expands(tmp_path):
    _write_module(tmp_path, 'pkg/__init__.py', '')
    _write_module(tmp_path, 'pkg/submod.py', 'def foo(x):\n    return x + 1\n')
    _write_module(
        tmp_path,
        'usermod_b.py',
        '''
        import pkg.submod as sm
        def bar(x):
            return sm.foo(x)
        ''',
    )

    usermod = _import_temp_module(tmp_path, 'usermod_b')
    try:
        with _TempSysPath(tmp_path):
            lib = Liberator()
            lib.add_dynamic(usermod.bar, eager=True)
            lib.expand(['pkg'])
            text = lib.current_sourcecode()
            ns = {}
            exec(text, ns, ns)
            assert ns['bar'](1) == 2
    finally:
        _cleanup_module('usermod_b')
        _cleanup_module('pkg')
        _cleanup_module('pkg.submod')


def test_expand_does_not_assert_for_os_path_alias(tmp_path):
    _write_module(
        tmp_path,
        'usermod_c.py',
        '''
        import os.path as osp
        def f(a, b):
            return osp.join(a, b)
        ''',
    )

    usermod = _import_temp_module(tmp_path, 'usermod_c')
    try:
        lib = Liberator()
        lib.add_dynamic(usermod.f, eager=True)
        lib.expand(['os'])
        text = lib.current_sourcecode()
        assert 'def f' in text
        ns = {}
        exec(text, ns, ns)
        got = ns['f']('a', 'b')
        assert got.endswith('a' + os.sep + 'b')
    finally:
        _cleanup_module('usermod_c')


def test_expand_internal_imports_no_docstring_or_alias_break(tmp_path):
    _write_module(tmp_path, 'pkg/__init__.py', '')
    _write_module(tmp_path, 'pkg/submod.py', 'def foo(x):\n    return x + 1\n')
    _write_module(
        tmp_path,
        'usermod_d.py',
        '''
        def g(x):
            import pkg.submod as sm
            return sm.foo(x)

        def h(x):
            """kept"""
            import pkg.submod as sm
            return sm.foo(x)
        ''',
    )

    usermod = _import_temp_module(tmp_path, 'usermod_d')
    try:
        with _TempSysPath(tmp_path):
            lib = Liberator(expand_internal_imports=True)
            lib.add_dynamic(usermod.g, eager=True)
            lib.add_dynamic(usermod.h, eager=True)
            lib.expand(['pkg'])
            text = lib.current_sourcecode()
            ns = {}
            exec(text, ns, ns)
            assert ns['g'](1) == 2
            assert ns['h'](1) == 2
            assert ns['h'].__doc__ == 'kept'
    finally:
        _cleanup_module('usermod_d')
        _cleanup_module('pkg')
        _cleanup_module('pkg.submod')


def test_definitionvisitor_parse_module_sets_modpath():
    import liberator.core as core
    visitor = DefinitionVisitor.parse(module=core)
    assert visitor.modpath == core.__file__
    assert visitor.modname == core.__name__


@pytest.mark.skipif(importlib.util.find_spec('parso') is None, reason='requires parso')
def test_starfinder_multiple_stars_association(tmp_path):
    from liberator.starfinder import find_import_stars

    _write_module(tmp_path, 'pkg/__init__.py', '')
    _write_module(
        tmp_path,
        'pkg/moda.py',
        '''
        __all__ = ['foo']
        def foo(x):
            return x + 1
        ''',
    )
    _write_module(
        tmp_path,
        'pkg/modb.py',
        '''
        def bar(x):
            return x + 1
        def _hidden(x):
            return x
        ''',
    )

    text = textwrap.dedent(
        '''
        from pkg.moda import *
        from pkg.modb import *
        x = foo(1)
        y = bar(2)
        '''
    )

    sys.path.insert(0, str(tmp_path))
    try:
        out = find_import_stars(text)
    finally:
        sys.path.pop(0)

    assert 'from pkg.moda import foo' in out
    assert 'from pkg.modb import bar' in out
    assert 'from pkg.moda import bar' not in out
    assert 'from pkg.modb import foo' not in out
