from setuptools import setup

setup(name="tram_lab_ros", version="0.1.0", packages=["tram_lab_ros"],
      data_files=[("share/ament_index/resource_index/packages", ["resource/tram_lab_ros"]),
                  ("share/tram_lab_ros", ["package.xml"])],
      install_requires=["setuptools"], zip_safe=True,
      maintainer="Odometry team", maintainer_email="team@example.invalid",
      description="ROS adapter for tram odometry experiments", license="MIT",
      entry_points={"console_scripts": ["estimator = tram_lab_ros.node:main"]})
