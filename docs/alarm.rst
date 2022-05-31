Notes on Arch Linux ARM
=======================

devtools
--------

Use ``devtools-archlinuxcn`` and manually setup for aarch64:

.. code-block:: sh

  ln -s archbuild /usr/bin/extra-aarch64-build
  cd /usr/share/devtools
  sed 's/x86[-_]64/aarch64/g' makepkg-x86_64.conf > makepkg-aarch64.conf

``alarm/devtools-alarm`` is broken because ``MAKEFLAGS`` and ``PACKAGER`` aren't passed in. (It also doesn't ship ``extra-aarch64-build``)

``archlinuxcn/devtools-arm-git`` is broken because it reports errors and bails out very early.

The alarm mirror URL is different and ``arch-nspawn`` can't handle it correctly. Let's just copy it:

.. code-block:: diff
  :caption: arch-nspawn.patch

  --- arch-nspawn.orig	2022-05-31 21:28:24.956220022 +0800
  +++ arch-nspawn	2022-05-31 21:28:33.356338236 +0800
  @@ -310,29 +310,6 @@
          mapfile -t cache_dirs < <($pacconf_cmd CacheDir)
  fi
  
  -# shellcheck disable=2016
  -host_mirrors=($($pacconf_cmd --repo extra Server 2> /dev/null | sed -r 's#(.*/)extra/os/.*#\1$repo/os/$arch#'))
  -
  -for host_mirror in "${host_mirrors[@]}"; do
  -	if [[ $host_mirror == *file://* ]]; then
  -		host_mirror=$(echo "$host_mirror" | sed -r 's#file://(/.*)/\$repo/os/\$arch#\1#g')
  -		for m in "$host_mirror"/pool/*/; do
  -			in_array "$m" "${cache_dirs[@]}" || cache_dirs+=("$m")
  -		done
  -	fi
  -done
  -
  -while read -r line; do
  -	mapfile -t lines < <($pacconf_cmd --config "${pac_conf:-$working_dir/etc/pacman.conf}" \
  -		--repo $line Server | sed -r 's#(.*/)[^/]+/os/.+#\1#')
  -	for line in "${lines[@]}"; do
  -		if [[ $line = file://* ]]; then
  -			line=${line#file://}
  -			in_array "$line" "${cache_dirs[@]}" || cache_dirs+=("$line")
  -		fi
  -	done
  -done < <($pacconf_cmd --config "${pac_conf:-$working_dir/etc/pacman.conf}" --repo-list)
  -
  mount_args+=("--bind=${cache_dirs[0]//:/\\:}")
  
  for cache_dir in "${cache_dirs[@]:1}"; do
  @@ -344,7 +321,8 @@
          unshare --fork --pid gpg --homedir "$working_dir"/etc/pacman.d/gnupg/ --no-permission-warning --quiet --batch --import --import-options import-local-sigs "$(pacman-conf GpgDir)"/pubring.gpg >/dev/null 2>&1
          pacman-key --gpgdir "$working_dir"/etc/pacman.d/gnupg/ --import-trustdb "$(pacman-conf GpgDir)" >/dev/null 2>&1
  
  -	printf 'Server = %s\n' "${host_mirrors[@]}" >"$working_dir/etc/pacman.d/mirrorlist"
  +	# The alarm mirror URL is different and this script can't handle it correctly. just copy it.
  +	cp /etc/pacman.d/mirrorlist "$working_dir/etc/pacman.d/mirrorlist"
  
          [[ -n $pac_conf ]] && cp "$pac_conf" "$working_dir/etc/pacman.conf"
          [[ -n $makepkg_conf ]] && cp "$makepkg_conf" "$working_dir/etc/makepkg.conf"
