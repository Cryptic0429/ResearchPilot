import sys

from .cli import main

try:
    main()
except Exception as error:
    sys.exit('错误：' + str(error))
