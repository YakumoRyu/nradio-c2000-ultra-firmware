# Local compatibility recipe for the pinned Python 3.13 toolchain.
include $(TOPDIR)/rules.mk

PKG_NAME:=python-yarl
PKG_VERSION:=1.25.1
PKG_RELEASE:=1
PYPI_NAME:=yarl
PKG_HASH:=03dd38de09bc213e9a8b29761eec33ee1d5318dac0e49d8af36e4d27830e23a7
PKG_LICENSE:=Apache-2.0
PKG_LICENSE_FILES:=LICENSE
PKG_BUILD_DEPENDS:=python-setuptools/host python-expandvars/host python-cython/host

include $(TOPDIR)/feeds/packages/lang/python/pypi.mk
include $(INCLUDE_DIR)/package.mk
include $(TOPDIR)/feeds/packages/lang/python/python3-package.mk

define Package/python3-yarl
  SECTION:=lang
  CATEGORY:=Languages
  SUBMENU:=Python
  TITLE:=yarl for Python 3
  URL:=https://pypi.org/project/yarl/
  DEPENDS:=+python3-light +python3-idna +python3-multidict +python3-propcache
endef

$(eval $(call Py3Package,python3-yarl))
$(eval $(call BuildPackage,python3-yarl))
$(eval $(call BuildPackage,python3-yarl-src))
