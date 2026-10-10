# Local compatibility recipe for the pinned Python 3.13 toolchain.
include $(TOPDIR)/rules.mk

PKG_NAME:=python-propcache
PKG_VERSION:=0.5.4
PKG_RELEASE:=1
PYPI_NAME:=propcache
PKG_HASH:=ff6b113f50bc066a698db5d944d2c6dc7507168dd3341e255a8892fd0715a558
PKG_LICENSE:=Apache-2.0
PKG_LICENSE_FILES:=LICENSE
PKG_BUILD_DEPENDS:=python-setuptools/host python-expandvars/host python-cython/host

include $(TOPDIR)/feeds/packages/lang/python/pypi.mk
include $(INCLUDE_DIR)/package.mk
include $(TOPDIR)/feeds/packages/lang/python/python3-package.mk

define Package/python3-propcache
  SECTION:=lang
  CATEGORY:=Languages
  SUBMENU:=Python
  TITLE:=propcache for Python 3
  URL:=https://pypi.org/project/propcache/
  DEPENDS:=+python3-light
endef

$(eval $(call Py3Package,python3-propcache))
$(eval $(call BuildPackage,python3-propcache))
$(eval $(call BuildPackage,python3-propcache-src))
