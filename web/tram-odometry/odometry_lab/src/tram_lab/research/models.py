"""One fixed traction-only profile on the existing lab scheduler, not a new champion."""
from copy import deepcopy
from ..hack_adapter import profile

MODEL_ID = 'hack_v8_traction_only'
SOURCE_COMMIT = 'da3467c3b40900b2e08e933722ef84a09fe44837'
TRACTION = {'total_motor_torque_nm': 3149.748421403977,
            'max_power_w': 429127.7144908343}


def candidate_defaults():
    doc = profile('hack_v8')
    core = deepcopy(doc['config'])
    # A different base must not silently inherit an old experimental identity.
    required = {'total_motor_torque_nm': 2905.0616664738573,
                'max_power_w': 280873.5334860941,
                'max_brake_force_n': 45568.80940352644,
                'adaptation_tau_s': .5, 'common_mode_quarantine_s': 1.5}
    if any(core.get(k) != v for k, v in required.items()):
        raise ValueError('Traction-only requires the pinned v8 baseline')
    core.update(TRACTION)
    return dict(profile='hack_v8', core=core, readout=deepcopy(doc['readout']), wheel_scale=1/3.6)


def register(add, specs):
    add(MODEL_ID, 'v8 · traction-only (эксперимент)',
        'tram_lab.hack_adapter:HackEstimator', candidate_defaults())
    specs[MODEL_ID]['research'] = dict(
        status='PREPARED_NOT_ACCURACY_VALIDATED', source_commit=SOURCE_COMMIT,
        source_repository='jabrailkhalil/hack', changed_fields=list(TRACTION),
        scheduler='odometry_lab receipt clock', training=False,
        native_development={'status': 'DO_NOT_PROMOTE', 'target_vehicle': '30618',
            'target_fault_error_change_percent': 9.935269904902654,
            'all_fault_error_change_percent': -1.1643567545644329,
            'all_full_faulted_distance_change_percent': 1.06001800411486,
            'note': 'Measured on native source clock, not this lab receipt clock'},
        note='Торможение v8 сохранено. Исторические native RMSE не относятся к этому replay.')
