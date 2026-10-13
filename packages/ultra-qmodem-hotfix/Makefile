include $(TOPDIR)/rules.mk

PKG_NAME:=ultra-qmodem-hotfix
PKG_VERSION:=20261013
PKG_RELEASE:=1
PKGARCH:=all

include $(INCLUDE_DIR)/package.mk

define Package/ultra-qmodem-hotfix
  SECTION:=net
  CATEGORY:=Network
  TITLE:=Ultra QModem consecutive-error hotfix
  DEPENDS:=+qmodem +python3
endef

define Package/ultra-qmodem-hotfix/description
  Correct QModem's accumulated AT failure count on NRadio C2000 Ultra.
  Preserve local configuration; retain a checked source backup and rollback.
endef

define Build/Compile
endef

define Package/ultra-qmodem-hotfix/install
	$(INSTALL_DIR) $(1)/usr/libexec
	$(INSTALL_BIN) ./files/ultra-qmodem-hotfix $(1)/usr/libexec/ultra-qmodem-hotfix
endef

define Package/ultra-qmodem-hotfix/postinst
#!/bin/sh
if [ -z "$${IPKG_INSTROOT:-}" ]; then
  /usr/libexec/ultra-qmodem-hotfix apply --activate || exit $$?
fi
exit 0
endef

$(eval $(call BuildPackage,ultra-qmodem-hotfix))
