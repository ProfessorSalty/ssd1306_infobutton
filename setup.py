# -*- coding: utf-8 -*-
from setuptools import setup

packages = \
['ssd1306_infobutton']

package_data = \
{'': ['*']}

install_requires = \
['luma.oled>=3.5.0,<4.0.0', 'rpi.gpio>=0.7.0,<0.8.0']

setup_kwargs = {
    'name': 'ssd1306-infobutton',
    'version': '0.1.3',
    'description': 'A script to control a SSD1306 OLED display with a button on the Raspberry Pi',
    'long_description': None,
    'author': 'Greg Smith',
    'author_email': 'gregory_smith@gregoftheweb.com',
    'maintainer': None,
    'maintainer_email': None,
    'url': None,
    'packages': packages,
    'package_data': package_data,
    'install_requires': install_requires,
    'python_requires': '>=3.7,<4.0',
}


setup(**setup_kwargs)
