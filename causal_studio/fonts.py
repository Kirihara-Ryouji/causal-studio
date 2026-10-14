"""Native Chinese font families for desktop platforms."""
import sys

UI_FONT = "PingFang SC" if sys.platform == "darwin" else "Microsoft YaHei UI"
TEXT_FONT = "PingFang SC" if sys.platform == "darwin" else "Microsoft YaHei"
