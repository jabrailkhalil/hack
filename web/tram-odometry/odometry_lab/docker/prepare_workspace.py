"""Materialize the supplied message package and repair build-only metadata."""
import hashlib
import json
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

source = Path("/dataset/tram_vehicle_msgs")
dest = Path("/opt/ros_ws/src/tram_vehicle_msgs")
shutil.copytree(source, dest, dirs_exist_ok=True)
manifest = dest / "package.xml"
before = hashlib.sha256(manifest.read_bytes()).hexdigest()
tree = ET.parse(manifest)
patches = []
if not tree.getroot().findall("maintainer"):
    node = ET.SubElement(tree.getroot(), "maintainer", {"email": "lab@example.invalid"})
    node.text = "Local odometry lab build"
    tree.write(manifest, encoding="utf-8", xml_declaration=True)
    patches.append("Added mandatory maintainer to workspace copy only; source package lacks one.")
message_hashes = {}
for path in sorted((source / "msg").glob("*.msg")):
    original = hashlib.sha256(path.read_bytes()).hexdigest()
    assert hashlib.sha256((dest / "msg" / path.name).read_bytes()).hexdigest() == original
    message_hashes[path.name] = original
report = {"patches": patches, "original_package_xml_sha256": before,
          "workspace_package_xml_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
          "unchanged_msg_sha256": message_hashes}
output = Path("/artifacts")
if output.is_dir():
    (output / "workspace_preparation.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report))
