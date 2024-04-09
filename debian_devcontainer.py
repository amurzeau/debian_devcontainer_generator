import os
import argparse
import shutil
from debian.deb822 import Deb822, PkgRelation
from debian.changelog import Changelog

def get_apt_package_from_build_depends_relation(package_or_list) -> str:
     # Find first non restricted package in "pkg1 | pkg2 | ..." list
    package_to_add = None
    for package in package_or_list:
        if package['arch'] is not None:
            # Skip by default if archs restriction don't have "!"
            skip_package = package['arch'][0].enabled
            arch_restriction: PkgRelation.ArchRestriction
            for arch_restriction in package['arch']:
                if arch_restriction.arch == "amd64" and arch_restriction.enabled:
                    skip_package = False
                    break
                elif arch_restriction.arch == "amd64" and not arch_restriction.enabled:
                    skip_package = True
                    break
            if not skip_package:
                package_to_add = package
                break
        else:
            package_to_add = package
            break

    if not package_to_add:
        raise Exception(f"Unresolvable dependency: {package_or_list}")

    apt_package = package_to_add['name']
    if package_to_add['archqual'] is not None:
        apt_package += f":{package_to_add['archqual']}"

    return apt_package

def generate_devcontainer(package_location):
    package_build_depends = []
    package_distribution = ""
    
    print(f"Generating .devcontainer in {package_location}")

    print("Parsing debian/changelog to read target distribution")
    with open(f"{package_location}/debian/changelog", "r") as fh:
        changelog = Changelog(fh, max_blocks=1)
        if changelog.distributions is None:
            raise Exception("Invalid file debian/changelog, distribution not found")
        package_distribution = changelog.distributions

    print("Parsing debian/control to retrieve dependencies")
    with open(f"{package_location}/debian/control", "r") as fh:
        for paragraph in Deb822.iter_paragraphs(fh):
            for depends_type in ['Build-Depends', 'Build-Depends-Indep', 'Build-Depends-Arch']:
                if depends_type in paragraph:
                        depends: PkgRelation = PkgRelation.parse_relations(paragraph[depends_type])
                        for package_or_list in depends:
                            apt_package = get_apt_package_from_build_depends_relation(package_or_list)
                            package_build_depends.append(apt_package)

    script_dir = os.path.dirname(os.path.realpath(__file__))
    os.makedirs(f"{package_location}/.devcontainer", exist_ok=True)

    shutil.copyfile(f"{script_dir}/devcontainer_template/devcontainer.json",
                    f"{package_location}/.devcontainer/devcontainer.json")
    
    with open(f"{script_dir}/devcontainer_template/Dockerfile.in", "r") as fh:
        dockerfile_content = fh.read()

        dockerfile_content = dockerfile_content.replace("{{debian_image_tag}}", package_distribution.replace("-backports", ""))

        if "backports" in package_distribution:
            dockerfile_content = dockerfile_content.replace("{{apt_additional_args}}", f" -t {package_distribution}")

        dockerfile_content = dockerfile_content.replace("{{build_depends}}", " \\\n\t".join(package_build_depends))

    with open(f"{package_location}/.devcontainer/Dockerfile", "w") as fh:
        fh.write(dockerfile_content)
        fh.write("\n")
    
    extend_diff_ignore = 'extend-diff-ignore = "^\\.devcontainer/"'
    with open(f"{package_location}/debian/source/options", "r+") as fh:
        for line in fh:
            if extend_diff_ignore in line:
                break
        else: # not found, we are at the eof
            fh.write(extend_diff_ignore) # append missing data
            fh.write("\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Generate .devcontainer from debian/control')
    parser.add_argument('package_location', type=str,
                        help='location of the package', default=os.getcwd())

    args = parser.parse_args()
    generate_devcontainer(args.package_location)