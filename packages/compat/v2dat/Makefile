include $(TOPDIR)/rules.mk

PKG_NAME:=v2dat
PKG_VERSION:=2022.12.15~47b8ee51
PKG_RELEASE:=4
PKG_SOURCE_VERSION:=47b8ee51fb528e11e1a83453b7e767a18d20d1f7
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.gz
PKG_SOURCE_URL:=https://codeload.github.com/urlesistiana/v2dat/tar.gz/$(PKG_SOURCE_VERSION)?
PKG_HASH:=dca45a31006aca3dba5f543f6990ca755ffb2bde8e533cc2bbe6bac9ec12f157
PKG_BUILD_DIR:=$(BUILD_DIR)/$(PKG_NAME)-$(PKG_SOURCE_VERSION)
PKG_LICENSE_FILES:=LICENSE
PKG_BUILD_DEPENDS:=golang/host
PKG_BUILD_PARALLEL:=1
PKG_BUILD_FLAGS:=no-mips16
GO_PKG:=github.com/urlesistiana/v2dat

include $(INCLUDE_DIR)/package.mk
include $(TOPDIR)/feeds/packages/lang/golang/golang-package.mk

define Package/v2dat
  SECTION:=net
  CATEGORY:=Network
  TITLE:=Unpack V2Ray routing data
  URL:=https://github.com/urlesistiana/v2dat
  DEPENDS:=$(GO_ARCH_DEPENDS)
endef

$(eval $(call GoBinPackage,v2dat))
$(eval $(call BuildPackage,v2dat))
