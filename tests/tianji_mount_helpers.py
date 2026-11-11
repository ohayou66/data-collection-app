"""Frame conversions for motion fixtures recorded before the flange update."""
import numpy as np
from marvin_teleop.geometry import inverse, transform


def right_to_left_tcp(models):
    # Derive the pairing from the current physical FK, allowing each arm's
    # confirmed mounting angle instead of assuming a fixed TCP reflection.
    left, right = models.arms['left'], models.arms['right']
    paired = inverse(right.fk(np.zeros(7))) @ left.tracking_mirror.world @ left.fk(np.zeros(7))
    # Remove ~1e-15 m/rad cancellation noise from the two world FK chains.
    return paired.round(12)


def previous_right_tool():
    return (transform([0, 0, 0], [0, 0, 3 * np.pi / 4])
            @ transform([0, 0, .142225549599], [0, -np.pi / 2, -np.pi / 4]))
