from setuptools import setup
from glob import glob

setup(
    name='reserve_odometry', version='0.1.0', packages=['reserve_odometry'],
    data_files=[('share/ament_index/resource_index/packages', ['resource/reserve_odometry']),
                ('share/reserve_odometry', ['package.xml']),
                ('share/reserve_odometry/launch', glob('launch/*.launch.py')),
                ('share/reserve_odometry/config', glob('config/*.yaml'))],
    install_requires=['setuptools'], zip_safe=True,
    maintainer='Hackathon team', maintainer_email='78273416+jabrailkhalil@users.noreply.github.com',
    description='Adaptive model-based reserve tram odometry', license='LicenseRef-Proprietary',
    entry_points={'console_scripts': ['odometry_node = reserve_odometry.node:main']},
)
