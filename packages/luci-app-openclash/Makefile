include $(TOPDIR)/rules.mk

PKG_NAME:=luci-app-openclash
PKG_VERSION:=0.48.002
PKG_RELEASE:=ultra1
PKG_SOURCE:=luci-app-openclash_$(PKG_VERSION)_all.ipk
PKG_SOURCE_URL:=https://github.com/vernesong/OpenClash/releases/download/v$(PKG_VERSION)/
PKG_HASH:=f3f0d0514553aea8d542c62dc52ac26d1f79dbda24204280f1cb8ea7fff71e9e
PKG_LICENSE:=GPL-3.0
PKG_BUILD_DIR:=$(BUILD_DIR)/$(PKG_NAME)-$(PKG_VERSION)-ultra1

include $(INCLUDE_DIR)/package.mk

define Package/$(PKG_NAME)
  SECTION:=luci
  CATEGORY:=LuCI
  SUBMENU:=3. Applications
  TITLE:=OpenClash with Ultra LuCI compatibility
  PKGARCH:=all
  DEPENDS:=+luci-compat +dnsmasq-full +bash +curl +ca-bundle +ip-full +ruby +ruby-yaml +kmod-tun +unzip
endef

define Build/Prepare
	$(INSTALL_DIR) $(PKG_BUILD_DIR)/archive $(PKG_BUILD_DIR)/root
	tar -xzf $(DL_DIR)/$(PKG_SOURCE) -C $(PKG_BUILD_DIR)/archive
	tar -xzf $(PKG_BUILD_DIR)/archive/data.tar.gz -C $(PKG_BUILD_DIR)/root
	grep -o 'data-tab' $(PKG_BUILD_DIR)/root/usr/lib/lua/luci/view/openclash/config_upload.htm | wc -l | grep -qx 5
	grep -o 'data-tab' $(PKG_BUILD_DIR)/root/www/luci-static/resources/openclash/js/config_upload.js | wc -l | grep -qx 6
	sed -i 's/data-tab/data-oc-tpl-tab/g' $(PKG_BUILD_DIR)/root/usr/lib/lua/luci/view/openclash/config_upload.htm $(PKG_BUILD_DIR)/root/www/luci-static/resources/openclash/js/config_upload.js
endef

define Build/Configure
endef
define Build/Compile
endef

define Package/$(PKG_NAME)/install
	$(CP) $(PKG_BUILD_DIR)/root/. $(1)/
endef

define Package/$(PKG_NAME)/preinst
#!/bin/sh
if [ -f /etc/config/openclash ] && [ ! -f /tmp/openclash.bak ]; then
 cp -f /etc/config/openclash /tmp/openclash.bak
 cp -rf /etc/openclash /tmp/openclash
 cp -rf /usr/share/openclash/ui /tmp/openclash_ui
 cp -rf /www/luci-static/resources/openclash/pac /tmp/pac
fi
exit 0
endef

define Package/$(PKG_NAME)/prerm
#!/bin/sh
[ -n "$$(pidof clash)" ] && /etc/init.d/openclash stop 2>/dev/null
if [ -f /etc/config/openclash ] && [ ! -f /tmp/openclash.bak ]; then
 cp -f /etc/config/openclash /tmp/openclash.bak
 cp -rf /etc/openclash /tmp/openclash
 cp -rf /usr/share/openclash/ui /tmp/openclash_ui
 cp -rf /www/luci-static/resources/openclash/pac /tmp/pac
fi
exit 0
endef

$(eval $(call BuildPackage,$(PKG_NAME)))
