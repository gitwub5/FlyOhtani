"""FlyOhtani v2 -- a real-scale Drosophila body, driven by a connectome-derived
circuit, learning to hit a pitched ball.

Package layout (docs/PLAN.md). Only the modules that have real content exist;
a directory appears when its Phase starts, not before:

    units    unit convention (mm / g / uN) -- Phase 0, done
    sense    eye camera, ball detection, temporal tracking -- Phase 0 (carried
             over), re-validated in Phase 3
    body     NeuroMechFly-jointed forelegs + bat -- Phase 1
    world    scaled mini ballpark, pitch launcher, contact -- Phase 2
    brain    connectome loader, LIF circuit, plasticity -- Phase 4
    task     gym env, reward versions, episode protocol -- Phase 5
    record   episode bundles -- Phase 6
    viewer   4-pane HTML playback -- Phase 6
"""
