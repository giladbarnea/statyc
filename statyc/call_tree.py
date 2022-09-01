from __future__ import annotations
import ast
import builtins
import inspect
from collections import OrderedDict
from pathlib import Path
from typing import Any

import click

BUILTIN_NAMES = set(map(str, builtins.__dict__))


class Module(ast.Module):

    def __init__(self, source, filename) -> None:
        super().__init__()
        self.__dict__ = ast.parse(source, filename).__dict__
        self.name = inspect.getmodulename(filename)
        # names: [ { name: ... } ]
        # module? : str
        self.imports = [node for node in ast.walk(self) if isinstance(node, (ast.Import, ast.ImportFrom))]
        self.function_defs = [FunctionDef(node, self) for node in ast.walk(self) if isinstance(node, ast.FunctionDef)]

    def get_function_def_by_name(self, name) -> FunctionDef:
        return next((fn_def for fn_def in self.function_defs if fn_def.name == name), None)

    def get_import_by_name(self, name) -> ast.Import | ast.ImportFrom:
        for imprt in self.imports:
            for alias in imprt.names:
                if alias.asname:
                    if alias.asname == name:
                        return imprt
                    continue
                if alias.name == name:
                    return imprt

class FunctionDef(ast.FunctionDef):

    def __init__(self, function_def: ast.FunctionDef, containing_module: Module) -> None:
        super().__init__()
        self.__dict__ = function_def.__dict__
        self.containing_module = containing_module


class Call(ast.Call):

    def __init__(self, call: ast.Call, containing_module: Module) -> None:
        super().__init__()
        self.__dict__ = call.__dict__
        self.containing_module = containing_module
        if isinstance(self.func, ast.Name):
            name = self.func.id
            if function_def:=self.containing_module.get_function_def_by_name(name):
                parent = self.containing_module.name
            else:
                print(f'{name = !r} not a function definition in {self.containing_module.name} module; '
                      f'must be `from ... import {name}` or `{name} = foo.{name}`')
        elif isinstance(self.func, ast.Attribute):
            name = self.func.attr
            if isinstance(self.func.value, ast.Name):
                parent = self.func.value.id
            else:
                print(f'not implemented, {self.func.value = } ({type(self.func.value)})')
        else:
            print(f'not implemented, {self.func = } ({type(self.func)})')
            return
        self.name = name
        self.parent = parent


def astdump(node):
    print(ast.dump(node, indent=4))


print_call_tree_cache = set()


def print_call_tree(call_tree, indent_level=0):
    if module_name not in call_tree:
        return
    if indent_level == 0:
        print_call_tree_cache.clear()
    for callee in call_tree[module_name]:
        if callee in print_call_tree_cache:
            continue
        print_call_tree_cache.add(callee)
        assert not isinstance(callee.func, ast.Subscript), astdump(callee.func)
        print(('· · ' * indent_level) + f'\x1b[1m{callee.func.id}\x1b[0m')
        subtree = get_call_tree(callee)
        # pprint(subtree)
        print_call_tree(subtree, indent_level + 1)


def get_call_tree(fn_def_or_call: ast.FunctionDef | ast.Call, containing_module: Module) -> dict:
    if isinstance(fn_def_or_call, ast.Call):
        # print(f'{fn_def_or_call = } | {fn_def_or_call.func = } | {fn_def_or_call.func.id = }')
        assert not isinstance(fn_def_or_call.func, ast.Subscript), astdump(fn_def_or_call.func)
        fn_def = get_function_def_by_name(fn_def_or_call.func.id)
        if not fn_def:
            return {}
        # print(f'{fn_def = }')
        return get_call_tree(fn_def)
    fn_def: ast.FunctionDef = fn_def_or_call
    callees_per_module = OrderedDict()
    for node in ast.walk(fn_def):
        if not isinstance(node, ast.Call):
            continue
        function_call: ast.Call = node
        call = Call(function_call, containing_module)
        if isinstance(function_call.func, ast.Name):
            # same module
            if function_call.func.id in BUILTIN_NAMES:
                continue
            callees_per_module.setdefault(module_name, [])
            if function_call not in callees_per_module[module_name]:
                print(function_call)
                callees_per_module[module_name].append(function_call)
        elif isinstance(function_call.func, ast.Attribute):
            while hasattr(function_call.func.value, 'func'):
                function_call = function_call.func.value
            try:
                callee_module_name = function_call.func.value.id
                callee_function_name = function_call.func.attr
            except AttributeError as e:
                print(repr(e), f'| function_call.func = ')
                # astdump(function_call.func)
            else:
                if callee_function_name in BUILTIN_NAMES:
                    continue
                callees_per_module.setdefault(callee_module_name, [])
                if callee_function_name not in callees_per_module[callee_module_name]:
                    callees_per_module[callee_module_name].append(callee_function_name)
        else:
            print('not implemented', function_call.func)
            astdump(function_call.func)
    return callees_per_module


@click.command()
@click.argument('file_path',
                type=click.Path(exists=True),
                default='/Users/gilad/dev/queryservice_master/app/service/queries/workflows/submit/v1/query_graph.py')
def main(file_path):
    file_text = Path(file_path).read_text()

    module = Module(file_text, file_path)
    # module_name = inspect.getmodulename(file_path)

    # names: [ { name: ... } ]
    # module? : str
    # imports = [node for node in ast.walk(module) if isinstance(node, (ast.Import, ast.ImportFrom))]
    # [astdump(imp) for imp in imports[:3]]

    # function_defs = [node for node in ast.walk(module) if isinstance(node, ast.FunctionDef)]

    validate_and_create_query_graph: FunctionDef = module.get_function_def_by_name('validate_and_create_query_graph')

    astdump(validate_and_create_query_graph)

    call_tree = get_call_tree(validate_and_create_query_graph, module)

    print_call_tree(call_tree)


if __name__ == "__main__":
    main()
