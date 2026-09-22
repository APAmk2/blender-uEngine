
def set_action_linear(action):
    # Baked Redux motion samples must not acquire Blender's Bézier overshoot.
    for fcurve in action.fcurves:
        for keyframe in fcurve.keyframe_points:
            keyframe.interpolation = "LINEAR"
        fcurve.update()
