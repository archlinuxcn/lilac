![lilac.png](https://github.com/archlinuxcn/artworks/raw/master/lilac-logo/example%20banners/banner-small.png)

[![Documentation Status](https://readthedocs.org/projects/lilac/badge/?version=latest)](https://lilac.readthedocs.io/en/latest/)

What does lilac do?
----

lilac is an automatic packaging tool for Arch Linux. It basically does the following things:

* figure out which packages have been updated or need rebuilding by calling [nvchecker](https://github.com/lilydjwg/nvchecker)
* figure out the order to build packages
* generate or update PKGBUILDs with custom configuration scripts ([common routines available](https://lilac.readthedocs.io/en/latest/api.html))
* call devtools to actually build packages
* handle built packages over to [archrepo2](https://github.com/lilydjwg/archrepo2) to update the repository database
* report any errors to maintainers via mail

Docs
----

* [lilac.yaml](https://archlinuxcn.github.io/lilac/)
* [lilac.py API](https://lilac.readthedocs.io/en/latest/api.html)
* [Setup and run your own](https://lilac.readthedocs.io/en/latest/)

License
-------

This project is licensed under GPLv3.
