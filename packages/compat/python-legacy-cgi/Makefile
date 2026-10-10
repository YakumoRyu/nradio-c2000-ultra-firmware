include $(TOPDIR)/rules.mk
PKG_NAME:=python-legacy-cgi
PKG_VERSION:=2.6.4
PKG_RELEASE:=1
PYPI_NAME:=legacy-cgi
PYPI_SOURCE_NAME:=legacy_cgi
PKG_HASH:=abb9dfc7835772f7c9317977c63253fd22a7484b5c9bbcdca60a29dcce97c577
PKG_LICENSE:=PSF-2.0
PKG_BUILD_DEPENDS:=python-hatchling/host
include $(TOPDIR)/feeds/packages/lang/python/pypi.mk
include $(INCLUDE_DIR)/package.mk
include $(TOPDIR)/feeds/packages/lang/python/python3-package.mk

define Package/python3-legacy-cgi
  SECTION:=lang
  CATEGORY:=Languages
  SUBMENU:=Python
  TITLE:=CGI compatibility modules for Python 3.13
  URL:=https://pypi.org/project/legacy-cgi/
  DEPENDS:=+python3-light +python3-email +python3-urllib +python3-pydoc
  PROVIDES:=python3-cgi python3-cgitb
endef
$(eval $(call Py3Package,python3-legacy-cgi))
$(eval $(call BuildPackage,python3-legacy-cgi))
$(eval $(call BuildPackage,python3-legacy-cgi-src))
