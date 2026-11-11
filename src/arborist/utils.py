"""Helpers that talk to the node editor and the scene."""

# from pathlib import Path

import bpy
from bpy.types import Context, NodeTree

from .props import props

# A node tree's bl_idname -> the group node that references it, so a tree can
# be dropped into an open editor as a single group node.
GROUP_NODE_IDNAME = {
    "GeometryNodeTree": "GeometryNodeGroup",
    "ShaderNodeTree": "ShaderNodeGroup",
    "CompositorNodeTree": "CompositorNodeGroup",
}


def node_tree(context: Context) -> NodeTree | None:
    """The node tree open in the node editor, following the editor into nested groups."""
    space = context.space_data
    if space is None or space.type != "NODE_EDITOR":
        return None
    return getattr(space, "edit_tree", None) or getattr(space, "node_tree", None)


def selected_node_tree(context: Context) -> NodeTree | None:
    """The node tree referenced by the active selected group node, or ``None``."""
    tree = node_tree(context)
    if tree is None:
        return None
    active = tree.nodes.active
    if active is not None and active.select:
        candidate = getattr(active, "node_tree", None)
        if isinstance(candidate, NodeTree):
            return candidate
    trees = [
        candidate
        for node in tree.nodes
        if node.select
        and isinstance(candidate := getattr(node, "node_tree", None), NodeTree)
    ]
    return trees[0] if len(trees) == 1 else None


def open_in_editor(context: Context, tree: NodeTree, *, pin: bool) -> bool:
    """Show ``tree`` in the current node editor.

    Pinned, the editor keeps showing the tree regardless of the active object;
    unpinned, a geometry editor follows the active object's active modifier.
    """
    space = context.space_data
    if space is None or space.type != "NODE_EDITOR":
        return False
    space.tree_type = tree.bl_idname
    space.pin = pin
    if pin:
        space.node_tree = tree
    return True


def apply_to_object(context: Context, tree: NodeTree) -> bpy.types.Object | None:
    """Add ``tree`` as a Geometry Nodes modifier on the active object."""
    if tree.bl_idname != "GeometryNodeTree":
        return None
    obj = context.active_object
    if obj is None:
        return None
    try:
        modifier = obj.modifiers.new(name=tree.name, type="NODES")
    except (RuntimeError, TypeError):
        return None  # object type has no modifiers (camera, empty, ...)
    modifier.node_group = tree
    obj.modifiers.active = modifier
    return obj


def drop_as_group(
    context: Context, tree: NodeTree, mouse: tuple[int, int] | None
) -> str | None:
    """Insert ``tree`` into the open editor as a group node grabbed by the mouse.

    Mirrors the Add menu: place the node at the cursor, then hand it to the
    translate-attach operator so it follows the mouse until dropped.
    Returns an error message, or ``None`` on success.
    """
    area = context.area
    space = context.space_data
    if area is None or space is None or space.type != "NODE_EDITOR":
        return "Run with the cursor in a Node Editor to drop a group"
    target = getattr(space, "edit_tree", None)
    group_idname = GROUP_NODE_IDNAME.get(tree.bl_idname)
    if target is None or group_idname is None or target.bl_idname != tree.bl_idname:
        return f"Open a {tree.bl_idname} in the editor to drop this group"
    if target == tree:
        return "Can't drop a group inside itself"

    group = target.nodes.new(group_idname)
    group.node_tree = tree
    group.show_options = False

    region = next((r for r in area.regions if r.type == "WINDOW"), None)
    if region is not None and mouse is not None:
        # Window coordinates -> region -> view, then undo the UI scale.
        x, y = region.view2d.region_to_view(mouse[0] - region.x, mouse[1] - region.y)
        ui_scale = context.preferences.system.ui_scale
        group.location = (x / ui_scale, y / ui_scale)

    for node in target.nodes:
        node.select = False
    group.select = True
    target.nodes.active = group

    if region is not None:
        with context.temp_override(area=area, region=region):
            try:
                bpy.ops.node.translate_attach_remove_on_cancel("INVOKE_DEFAULT")
            except RuntimeError:
                pass  # already placed at the cursor, just not grab-attached
    return None


def redraw_node_editors() -> None:
    wm = bpy.context.window_manager
    if wm is None:
        return
    for window in wm.windows:
        for area in window.screen.areas:
            if area.type == "NODE_EDITOR":
                area.tag_redraw()


# def push_node_to_py(nodegroup: bpy.types.NodeGroup, lib: Path, overwrite=True) -> Path:
#     """
#     Save the input node groups to python files using nodebpy

#     lib : the path to the global node folder.
#     It saves it there only if no file with the same name is found in subfolders.
#     If there is one, use its path instead. This allows organization
#     """
#     from nodebpy.export import to_python

#     def push(group: bpy.types.NodeGroup) -> Path:
#         matches = sorted(lib.rglob(f"{group.name}.py"))
#         path = matches[0] if matches else lib / f"{group.name}.py"
#         if path.exists() and not overwrite:
#             return path
#         path.parent.mkdir(parents=True, exist_ok=True)
#         code = to_python(group, top_level="class", in_place=True, props)
#         path.write_text(code)
#         return path

#     # Nested groups get their own files first, so each file's imports resolve.
#     for nested in getattr(nodegroup, "node_groups", ()):
#         push(nested)
#     return push(nodegroup)


# def pull_node_from_py(py_nodegroup: Path, overwrite=True):
#     """Convert back nodebpy node file into a Blender node group"""
#     from nodebpy.live import run_source

#     path = Path(bpy.path.abspath(str(py_nodegroup)))
#     if not path.suffix:
#         path = path.with_suffix(".py")
#     if not path.exists():
#         raise FileNotFoundError(f"No nodebpy file at {path}")

#     existing = bpy.data.node_groups.get(path.stem)
#     if existing is None or overwrite:
#         run_source(path.read_text(), filename=str(path))
#         redraw_node_editors()
