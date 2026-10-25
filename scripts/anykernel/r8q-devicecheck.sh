# SPDX-License-Identifier: GPL-2.0-only
# Fallback for r8q ports whose Android product name belongs to the donor ROM.
# Called only by the r8q AnyKernel device gate, before anykernel.sh runs.

r8q_read_dt() {
  local node="$1" base
  for base in /sys/firmware/devicetree/base /proc/device-tree; do
    if [ -r "$base/$node" ]; then
      tr '\000' '\n' < "$base/$node"
      return
    fi
  done
  return 1
}

r8q_has_boot_partition() {
  [ -b /dev/block/platform/soc/1d84000.ufshc/by-name/boot ]
}

r8q_port_devicecheck() {
  local model bootloader dt_model compatible platform
  model=$(getprop ro.boot.em.model 2>/dev/null)
  bootloader=$(getprop ro.boot.bootloader 2>/dev/null)
  [ -n "$bootloader" ] || bootloader=$(getprop ro.bootloader 2>/dev/null)
  platform=$(getprop ro.board.platform 2>/dev/null)
  dt_model=$(r8q_read_dt model)
  compatible=$(r8q_read_dt compatible)

  ui_print "r8q hardware check: model=$model bootloader=$bootloader platform=$platform"
  ui_print "Device tree: $dt_model"
  case "$model:$bootloader" in
    SM-G780G:G780G*|SM-G781B:G781B*) ;;
    *) ui_print "No matching supported Samsung EUR model/bootloader pair."; return 1 ;;
  esac
  case "$dt_model" in
    'Samsung R8Q '*|'Samsung SM-G781B'*) ;;
    *) ui_print "Device tree does not identify supported Samsung R8Q hardware."; return 1 ;;
  esac
  case "$compatible" in
    *qcom,kona*|*qcom,sm8250*) ;;
    *) ui_print "Expected kona/SM8250 device tree was not found."; return 1 ;;
  esac
  case "$platform" in
    kona|'') ;;
    *) ui_print "Platform contradicts Samsung R8Q/kona hardware."; return 1 ;;
  esac
  r8q_has_boot_partition || {
    ui_print "Expected r8q boot partition was not found."
    return 1
  }
  ui_print "Samsung r8q hardware verified; donor ROM product name accepted."
  return 0
}
