import bpy


def set_object_ray_visibility(
    obj: bpy.types.Object,
    *,
    diffuse: bool | None = None,
    glossy: bool | None = None,
    transmission: bool | None = None,
    scatter: bool | None = None,
    shadow: bool | None = None,
    camera: bool | None = None,
) -> None:
    """Set per-ray-type visibility on an object (Blender 5.0+ object properties)."""
    flags = (
        ('diffuse', 'visible_diffuse'),
        ('glossy', 'visible_glossy'),
        ('transmission', 'visible_transmission'),
        ('scatter', 'visible_volume_scatter'),
        ('shadow', 'visible_shadow'),
        ('camera', 'visible_camera'),
    )
    for kwarg_name, rna_name in flags:
        value = locals()[kwarg_name]
        if value is not None and hasattr(obj, rna_name):
            setattr(obj, rna_name, value)
