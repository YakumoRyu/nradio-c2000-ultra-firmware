# Local compatibility recipe for the pinned Python 3.13 toolchain.
include $(TOPDIR)/rules.mk

PKG_NAME:=python-multidict
PKG_VERSION:=6.9.1
PKG_RELEASE:=1
PYPI_NAME:=multidict
PKG_HASH:=0f06e60fa190aa7abd0914c2a766736fdc8e9f34878c4346338534b73d1b20e2
PKG_LICENSE:=Apache-2.0
PKG_LICENSE_FILES:=LICENSE
PKG_BUILD_DEPENDS:=python-setuptools/host

include $(TOPDIR)/feeds/packages/lang/python/pypi.mk
include $(INCLUDE_DIR)/package.mk
include $(TOPDIR)/feeds/packages/lang/python/python3-package.mk

define Package/python3-multidict
  SECTION:=lang
  CATEGORY:=Languages
  SUBMENU:=Python
  TITLE:=multidict for Python 3
  URL:=https://pypi.org/project/multidict/
  DEPENDS:=+python3-light
endef

$(eval $(call Py3Package,python3-multidict))
$(eval $(call BuildPackage,python3-multidict))
$(eval $(call BuildPackage,python3-multidict-src))
