

def find_import_stars(text):
    """
    Args:
        text (str): the python code to refactor

    Example:
        >>> # xdoctest: +REQUIRES(module:parso)
        >>> from liberator.starfinder import *  # NOQA
        >>> import ubelt as ub
        >>> text = ub.codeblock(
        >>>     '''
        >>>     import dis as dat
        >>>     from io import *
        >>>     from a.b import *
        >>>     from textwrap import *  # NOQA
        >>>     x = StringIO
        >>>     y = dedent
        >>>     ''')
        >>> final_text = find_import_stars(text)
        >>> print('----')
        >>> print('Text')
        >>> print('----')
        >>> print(ub.highlight_code(text))
        >>> print('----------')
        >>> print('Final Text')
        >>> print('----------')
        >>> print(ub.highlight_code(final_text))
    """
    import ast
    import parso
    import ubelt as ub
    from liberator.core import DefinitionVisitor

    def _public_exports(modname):
        modpath = ub.modname_to_modpath(modname)
        if modpath is None:
            return set()
        try:
            source = ub.Path(modpath).read_text()
        except Exception:
            return set()
        try:
            pt = ast.parse(source)
        except Exception:
            return set()

        explicit = None
        for node in pt.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == '__all__':
                        try:
                            value = ast.literal_eval(node.value)
                        except Exception:
                            value = None
                        if isinstance(value, (list, tuple)) and all(isinstance(v, str) for v in value):
                            explicit = set(value)
        if explicit is not None:
            return explicit

        visitor = DefinitionVisitor.parse(source=source, modpath=modpath, modname=modname)
        return {d.name for d in visitor.definitions.values() if not d.name.startswith('_')}
    import_star_infos = []
    mod = parso.parse(text)
    for node in mod.iter_imports():
        if len(node.children) > 1:
            a, b = node.children[0:2]
            y, z = node.children[-2:]
            parts_ayz = [a.get_code().strip(),
                         y.get_code().strip(),
                         z.get_code().strip()]
            flag = parts_ayz == ['from', 'import', '*']
            if flag:
                # This is an import * node we want to replace it
                # Use this to figure out stuff about the module
                modname = b.get_code().strip()
                modpath = ub.modname_to_modpath(modname)
                import_star_infos.append({
                    'node': node,
                    'modname': modname,
                    'modpath': modpath,
                })

    from liberator.core import undefined_names
    lines = text.split('\n')
    for info in reversed(import_star_infos):
        node = info['node']
        s = node.start_pos[0] - 1
        t = node.end_pos[0]
        del lines[s:t]

    new_code = '\n'.join(lines)

    names = undefined_names(new_code)
    # Now we need to associate which undefined name comes from which import *
    new_lines = []
    unmatched = set(names)
    for info in import_star_infos:
        modname = info['modname']
        exports = _public_exports(modname)
        associated = sorted(unmatched & exports)
        if associated:
            unmatched.difference_update(associated)
            associated_part = ', '.join(associated)
            new_lines.append(f'from {modname} import {associated_part}')
    # But if there is just one, then we can skip this check in some cases.
    final_text = '\n'.join(new_lines) + '\n' + new_code
    return final_text
