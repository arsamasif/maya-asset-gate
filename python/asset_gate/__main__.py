"""Allow ``python -m asset_gate``.

Delegates to the CLI and exits with its return code.

"""

import sys

from asset_gate import cli

sys.exit(cli.main())
