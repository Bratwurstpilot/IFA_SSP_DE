import urllib3

from bootstrap import bootstrap
from ssp_ui import main

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

if __name__ == "__main__":
    bootstrap()
    main()
