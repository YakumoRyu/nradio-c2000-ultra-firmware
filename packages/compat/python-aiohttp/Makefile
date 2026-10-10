# Local compatibility recipe for the pinned Python 3.13 toolchain.
include $(TOPDIR)/rules.mk

PKG_NAME:=python-aiohttp
PKG_VERSION:=3.14.3
PKG_RELEASE:=1
PYPI_NAME:=aiohttp
PKG_HASH:=9491196535a88924a60afd5b5f434b5b203b6cc616250878dbdb223a8f7844bc
PKG_LICENSE:=Apache-2.0 MIT
PKG_LICENSE_FILES:=LICENSE.txt
PKG_BUILD_DEPENDS:=python-setuptools/host python-pkgconfig/host

include $(TOPDIR)/feeds/packages/lang/python/pypi.mk
include $(INCLUDE_DIR)/package.mk
include $(TOPDIR)/feeds/packages/lang/python/python3-package.mk

define Package/python3-aiohttp
  SECTION:=lang
  CATEGORY:=Languages
  SUBMENU:=Python
  TITLE:=aiohttp for Python 3
  URL:=https://pypi.org/project/aiohttp/
  DEPENDS:=+python3-light +python3-asyncio +python3-email +python3-logging +python3-openssl +python3-urllib +python3-aiohappyeyeballs +python3-aiosignal +python3-attrs +python3-frozenlist +python3-multidict +python3-propcache +python3-yarl
endef

$(eval $(call Py3Package,python3-aiohttp))
$(eval $(call BuildPackage,python3-aiohttp))
$(eval $(call BuildPackage,python3-aiohttp-src))
