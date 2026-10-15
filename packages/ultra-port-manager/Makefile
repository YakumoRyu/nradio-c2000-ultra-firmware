include $(TOPDIR)/rules.mk

PKG_NAME:=ultra-port-manager
PKG_VERSION:=20261015
PKG_RELEASE:=1
PKGARCH:=all
PKG_LICENSE:=MIT

include $(INCLUDE_DIR)/package.mk

define Package/ultra-port-manager
  SECTION:=net
  CATEGORY:=Network
  TITLE:=C2000 Ultra physical port role manager
  DEPENDS:=+python3 +luci-compat +luci-lib-nixio +uci +ip-full
endef

define Package/ultra-port-manager/description
  Manage Ultra port 1 without replacing QModem's cellular interfaces.
  Includes authenticated UI, bounded discovery and timed configuration rollback.
endef

define Build/Compile
endef

define Package/ultra-port-manager/install
	$(INSTALL_DIR) $(1)
	$(CP) ./files/* $(1)/
	chmod 755 $(1)/usr/libexec/ultra-ports $(1)/usr/libexec/ultra-port-probe $(1)/usr/libexec/ultra-ports-install $(1)/etc/init.d/ultra-ports-guard
endef

define Package/ultra-port-manager/postinst
#!/bin/sh
if [ -z "$${IPKG_INSTROOT:-}" ]; then
  /usr/libexec/ultra-ports-install install || exit $$?
  /etc/init.d/ultra-ports-guard enable
fi
exit 0
endef

define Package/ultra-port-manager/prerm
#!/bin/sh
if [ -z "$${IPKG_INSTROOT:-}" ]; then
  /usr/libexec/ultra-ports-install remove || exit $$?
  /etc/init.d/ultra-ports-guard disable
fi
exit 0
endef

$(eval $(call BuildPackage,ultra-port-manager))
