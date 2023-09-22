#!/usr/bin/env python
import os
import re
import xml.dom.minidom as dom
from collections import defaultdict
from typing import Dict, List, Tuple


def _get_test_suites(test_src: str) -> List[dom.Element]:
    src_tree: dom.Document = dom.parse(test_src)
    src_root = src_tree.documentElement

    if src_root.nodeName == "testsuite":
        return [src_root]

    if src_root.nodeName == "testsuites":
        return [node for node in src_root.childNodes if node.nodeName == "testsuite"]

    raise NotImplementedError(src_root.nodeName)


def _add_test_detail_if_present(case_src: dom.Element, case_out: dom.Element, dom_out: dom.Document):
    failures = [node for node in case_src.childNodes if node.nodeName == "failure"]
    skipped = [node for node in case_src.childNodes if node.nodeName == "skipped"]
    errors = [node for node in case_src.childNodes if node.nodeName == "error"]
    detail = errors or failures or skipped
    if not detail:
        return

    detail_node = detail[0]
    message = detail_node.getAttribute("message") or ""
    detail_type = detail_node.getAttribute("type") or ""
    if detail_type:
        if not message.startswith("("):
            message = f"({message})"
        message = f"{detail_type}{message}"
    detail_out = dom_out.createElement(detail_node.nodeName)
    detail_out.setAttribute("message", message)
    detail_text = "".join([node.nodeValue for node in detail_node.childNodes if node.nodeValue])
    if detail_text:
        cdata = dom.CDATASection()
        cdata.nodeValue = detail_text
        detail_out.childNodes.append(cdata)
    case_out.childNodes.append(detail_out)


def _translate_test_case(
    case_src: dom.Element, dom_out: dom.Document, is_feature_file: bool
) -> Tuple[str, dom.Element]:
    classname = case_src.getAttribute("classname")
    test_name = case_src.getAttribute("name")
    duration = round(float(case_src.getAttribute("time") or "0") * 1000, 0)
    classname_dotsplit = classname.split(".")
    test_file = f"features/{classname_dotsplit[0]}.py" if is_feature_file else f"{'/'.join(classname_dotsplit)}.py"
    test_name = f"{'.'.join(classname_dotsplit[1:])} - {test_name}" if is_feature_file else test_name
    case_out = dom_out.createElement("testCase")
    case_out.setAttribute("name", test_name)
    case_out.setAttribute("duration", str(duration))
    _add_test_detail_if_present(case_src, case_out, dom_out)

    return test_file, case_out


def _get_tests_from_file(test_src: str, dom_out: dom.Document) -> Dict[str, List[dom.Element]]:
    is_feature_file = os.path.basename(test_src).startswith("TESTS-")
    test_suites = _get_test_suites(test_src)

    test_cases = []
    for suite in test_suites:
        test_cases.extend([node for node in suite.childNodes if node.nodeName == "testcase"])

    print(test_src, "suites", len(test_suites), "cases", len(test_cases))

    tests: Dict[str, List[dom.Element]] = defaultdict(list)

    for test_case in test_cases:
        test_file, case_out = _translate_test_case(test_case, dom_out, is_feature_file)
        tests[test_file].append(case_out)

    return tests


def _transform_coverage(reports_dir: str, output_sonar: str):
    src_coverage = os.path.join(reports_dir, "coverage.xml")
    out_coverage = os.path.join(output_sonar, "coverage.xml")

    if not os.path.exists(src_coverage):
        print("no coverage found")
        return

    print("transform:", src_coverage, out_coverage)
    with open(src_coverage, encoding="utf-8") as src:
        coverage = src.read()
        coverage = re.sub(r"<source>.*?</source>", "<source>.</source>", coverage)
        with open(out_coverage, "w+", encoding="utf-8") as out:
            out.write(coverage)


def _transform_xunit_results(reports_dir: str, output_sonar: str):
    src_junit = os.path.join(reports_dir, "junit")
    out_tests = os.path.join(output_sonar, "tests.xml")

    dom_out = dom.getDOMImplementation().createDocument(None, "testExecutions", None)
    dom_out.documentElement.setAttribute("version", "1")
    all_tests: Dict[str, List[dom.Element]] = defaultdict(list)

    for source_file in os.listdir(src_junit):
        if not source_file.endswith(".xml"):
            continue

        test_src = os.path.join(src_junit, source_file)
        found_tests = _get_tests_from_file(test_src=test_src, dom_out=dom_out)
        for path, tests in found_tests.items():
            all_tests[path].extend(tests)

    filenames = sorted(all_tests.keys())
    for filename in filenames:
        file_node = dom_out.createElement("file")
        file_node.setAttribute("path", filename)
        file_node.childNodes.extend(all_tests[filename])
        dom_out.documentElement.childNodes.append(file_node)

    with open(out_tests, "w+", encoding="utf-8") as writer:
        dom_out.writexml(writer, indent="", addindent="\t", newl="\n", encoding=None)


def main():
    """
    this is to convert the junit xml to a format compatible with sonar ...
    sonar is from the java world so expects junit classnames to actually relate to python modules
    it also doesn't understand .feature files ( 'unsupported language .feature' ) .. I pretend they are .py
    format is from https://docs.sonarqube.org/latest/analysis/generic-test/

    <testExecutions version="1">
        <file path="testx/ClassOneTest.xoo">
            <testCase name="test1" duration="5"/>
            <testCase name="test2" duration="500">
                <skipped message="short message">other</skipped>
            </testCase>
            <testCase name="test3" duration="100">
                <failure message="short">stacktrace</failure>
            </testCase>
            <testCase name="test4" duration="500">
                <error message="short">stacktrace</error>
            </testCase>
        </file>
    </testExecutions>

    """
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../"))
    reports_dir = os.path.join(root_dir, "reports")
    output_sonar = os.path.join(reports_dir, "sonar")
    os.makedirs(output_sonar, exist_ok=True)

    _transform_coverage(reports_dir, output_sonar)

    _transform_xunit_results(reports_dir, output_sonar)


if __name__ == "__main__":
    main()
