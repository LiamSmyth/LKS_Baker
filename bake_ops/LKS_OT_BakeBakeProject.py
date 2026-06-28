"""Run Cycles bake for one bake project from the project list."""

from __future__ import annotations

import bpy

from .helpers_bake_run import bake_project_has_bakable_groups, run_bake_project
from .static_utilities.bake_texture_derivatives import BakeMapSkipped, TextureDeriveSkip


class LKS_OT_BakeBakeProject(bpy.types.Operator):
    """Generate prep meshes, run Cycles bake, and wire preview maps on low materials."""
    bl_idname = 'object.lks_bake_bake_project'
    bl_label = 'Bake Project'
    bl_options = {'REGISTER'}

    project_index: bpy.props.IntProperty(
        name='Project Index',
        default=-1,
        description='Bake project index (-1 = active project)',
    )

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        if context.area is None or context.area.type != 'VIEW_3D':
            return False
        return len(context.scene.lks_bake_projects) > 0

    def _resolve_project_index(self, scene: bpy.types.Scene) -> int:
        if self.project_index >= 0:
            return self.project_index
        return scene.lks_active_bake_project_index

    def execute(self, context: bpy.types.Context) -> set[str]:
        scene = context.scene
        index = self._resolve_project_index(scene)
        if not (0 <= index < len(scene.lks_bake_projects)):
            self.report({'ERROR'}, 'No bake project to bake')
            return {'CANCELLED'}

        project = scene.lks_bake_projects[index]
        if not bake_project_has_bakable_groups(project):
            self.report(
                {'ERROR'},
                f"Project '{project.name}' needs high and low geometry across its bake groups",
            )
            return {'CANCELLED'}

        try:
            baked = run_bake_project(context, project)
        except BakeMapSkipped as exc:
            self.report({'WARNING'}, str(exc))
            return {'FINISHED'}
        except TextureDeriveSkip as exc:
            self.report({'WARNING'}, str(exc))
            return {'FINISHED'}
        except RuntimeError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}

        if not baked:
            self.report(
                {'WARNING'},
                'Bake finished with no map outputs — some maps may have been skipped',
            )
            return {'FINISHED'}

        map_ids = sorted({result.map_id for result in baked})
        self.report(
            {'INFO'},
            f"Baked {len(baked)} map(s) ({', '.join(map_ids)}) to {project.output_dir}",
        )
        return {'FINISHED'}
