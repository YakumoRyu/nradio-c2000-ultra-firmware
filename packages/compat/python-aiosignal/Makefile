# Local compatibility recipe for the pinned Python 3.13 toolchain.
include $(TOPDIR)/rules.mk

PKG_NAME:=python-aiosignal
PKG_VERSION:=1.4.0
PKG_RELEASE:=1
PYPI_NAME:=aiosignal
PKG_HASH:=f47eecd9468083c2029cc99945502cb7708b082c232f9aca65da147157b251c7
PKG_LICENSE:=Apache-2.0
PKG_LICENSE_FILES:=LICENSE
PKG_BUILD_DEPENDS:=python-setuptools/host

include $(TOPDIR)/feeds/packages/lang/python/pypi.mk
include $(INCLUDE_DIR)/package.mk
include $(TOPDIR)/feeds/packages/lang/python/python3-package.mk

define Package/python3-aiosignal
  SECTION:=lang
  CATEGORY:=Languages
  SUBMENU:=Python
  TITLE:=aiosignal for Python 3
  URL:=https://pypi.org/project/aiosignal/
  DEPENDS:=+python3-light +python3-frozenlist +python3-typing-extensions
endef

$(eval $(call Py3Package,python3-aiosignal))
$(eval $(call BuildPackage,python3-aiosignal))
$(eval $(call BuildPackage,python3-aiosignal-src))
