def is_list_of_dicts_with_keys(value, keys):
    if isinstance(value, list):
        return all(isinstance(item, dict) and all(key in item for key in keys) for item in value)
    return False


def format_installs_required(config):
    dependencies = []
    for k, v in config.items():
        if k == "python":
            continue
        elif is_list_of_dicts_with_keys(v, ["version", "markers"]):
            for package_version in v:
                version = package_version.get("version")
                markers = package_version.get("markers")
                dependencies.append(f"{k}{version} ; {markers}")
        else:
            dependencies.append(f"{k} ({v})")

    return dependencies
