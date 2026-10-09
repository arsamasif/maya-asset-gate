"""Command line interface: validate and publish SceneData JSON dumps.

Runs without Maya, so the same gate can be used in CI or on a farm after
the Maya adapter has dumped a scene to JSON::

    asset-gate validate chair.json --report report.json
    asset-gate validate chair.json --fix --write-fixed chair_fixed.json
    asset-gate publish chair.json --out publish/chair/v001
    asset-gate checks

"""

import argparse
import sys

from asset_gate import __version__
from asset_gate import config as config_mod
from asset_gate import gate
from asset_gate import registry
from asset_gate import report
from asset_gate import scene as scene_mod

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2


def main(argv=None):
    """Run the CLI.

    Args:
        argv (list): Arguments, defaults to ``sys.argv[1:]``.

    Returns:
        int: Exit code (0 ok, 1 validation failed, 2 bad input).

    """
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except (FileNotFoundError, ValueError, KeyError) as error:
        print(f"asset-gate: error: {error}", file=sys.stderr)
        return EXIT_USAGE


def _build_parser():
    parser = argparse.ArgumentParser(
        prog="asset-gate", description="Validate Maya assets and publish them to USD.")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate", help="run checks on a scene JSON dump")
    _add_common(validate)
    validate.add_argument("--fix", action="store_true", help="apply available fixes")
    validate.add_argument("--write-fixed", metavar="PATH", help="save the fixed scene JSON")
    validate.set_defaults(handler=_cmd_validate)

    publish = sub.add_parser("publish", help="validate, then write the USD asset")
    _add_common(publish)
    publish.add_argument("--out", required=True, help="output folder for the USD layers")
    publish.add_argument("--force", action="store_true", help="publish even if checks fail")
    publish.set_defaults(handler=_cmd_publish)

    checks = sub.add_parser("checks", help="list available checks")
    checks.add_argument("--plugins", action="append", default=[], metavar="DIR")
    checks.set_defaults(handler=_cmd_checks)
    return parser


def _add_common(parser):
    parser.add_argument("scene", help="SceneData JSON file")
    parser.add_argument("--config", help="JSON or YAML config file")
    parser.add_argument("--plugins", action="append", default=[], metavar="DIR",
                        help="extra check plugin folder (repeatable)")
    parser.add_argument("--report", metavar="PATH", help="write a JSON report")
    parser.add_argument("-v", "--verbose", action="store_true", help="list every issue")


def _prepare(args):
    config = config_mod.load(args.config) if args.config else {}
    scene = scene_mod.load(args.scene)
    context = gate.make_context(scene, config)
    checks = gate.load_checks(config, args.plugins)
    return context, checks


def _finish(args, context, results):
    print(report.format_console(results, context.scene.name, args.verbose))
    if args.report:
        report.write_json(results, args.report, context.scene.name)
        print(f"Report written to {args.report}")
    return EXIT_OK if report.summarize(results)["publishable"] else EXIT_FAILED


def _cmd_validate(args):
    context, checks = _prepare(args)
    results = gate.validate(context, checks, fix=args.fix)
    if args.write_fixed:
        scene_mod.save(context.scene, args.write_fixed)
        print(f"Fixed scene written to {args.write_fixed}")
    return _finish(args, context, results)


def _cmd_publish(args):
    context, checks = _prepare(args)
    try:
        results, written = gate.publish(context, args.out, checks, force=args.force)
    except gate.PublishBlocked as blocked:
        _finish(args, context, blocked.results)
        print("Publish blocked: validation failed (use --force to override).")
        return EXIT_FAILED
    _finish(args, context, results)
    print(report.banner("published"))
    for label, path in vars(written).items():
        print(f"{label:<8} {path}")
    return EXIT_OK


def _cmd_checks(args):
    found = registry.discover(plugin_dirs=args.plugins)
    print(report.banner("checks"))
    for check_id in found.ids():
        cls = found.get(check_id)
        fix = "fix" if cls.fixable() else "   "
        print(f"{check_id:<22} {cls.severity:<8} {fix}  {cls.description}")
    return EXIT_OK
