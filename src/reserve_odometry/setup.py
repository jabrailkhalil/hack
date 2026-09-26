from setuptools import setup

# The installed surface has exactly one supported pipeline, launcher and profile.
# Legacy source fixtures remain in Git for historical reproduction, NOT installed.
setup(
    name='reserve_odometry', version='0.8.1', packages=['reserve_odometry'],
    data_files=[('share/ament_index/resource_index/packages', ['resource/reserve_odometry']),
                ('share/reserve_odometry', ['package.xml']),
                ('share/reserve_odometry/launch', ['launch/odometry.launch.py']),
                ('share/reserve_odometry/config', ['config/champion_v8.yaml'])],
    install_requires=['setuptools'], zip_safe=True,
    maintainer='Hackathon team', maintainer_email='78273416+jabrailkhalil@users.noreply.github.com',
    description='Selected v8 reserve tram odometry pipeline', license='LicenseRef-Proprietary',
    entry_points={'console_scripts': [
        'guarded_odometry_node = reserve_odometry.guarded_node:main',
    ]},
)
