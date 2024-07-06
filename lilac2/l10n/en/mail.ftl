nonexistent-deps-subject = Non-existent dependencies is listed in lilac.yaml for { $pkg }
nonexistent-deps-body = lilac.yaml of package { $pkg } specifies repo_depends, but the (direct or indirect) {$count ->
    [one] dependency { $deps } is
   *[other] dependencies { $deps } are
  } not in this repository.

update_on_build-error = Error while checking update_on_build for %s

dependency-issue-subject = Dependency issue for %s
dependency-issue-failed = {$count ->
  [one] Dependency
 *[other] Dependencies
} { $faileddeps } for { $pkg } failed to build.
dependency-issue-failed-this-batch = {$count_deps ->
  [one] Dependency { $deps } for { $pkg } is
 *[other] Dependencies { $deps } for { $pkg } are
} missing, among which {$count_failed ->
  [one] { $faileddeps } has
 *[other] { $faileddeps } have
} failed this time.

aur-submit-error = Failed to submit %s to AUR

package-staged-subject = { $pkg } { $version } has been packaged just now
package-staged-body = The package has been placed in the staging directory, please check it and then publish manually.

too-much-output = Too much output, killed.

log-too-long = Log too long, omitting...

nvchecker-error-report = nvchecker error report

github-token-not-set = github token not configured, unable to retrieve Email address from GitHub
github-email-error = Error retrieving maintainer's Email address from GitHub: { $error }
github-email-private = GitHub user { $user } doesn't make their Email address public
unsupported-maintainer-info = Unsupported format: { $info }

maintainers-error-subject = maintainers for { $pkg } has errors
maintainers-error-body = The following maintainers information has errors, please fix:

packaging-error-subprocess-subject = Error packaging %s
packaging-error-subprocess =
    Command failed!
    
    Command { $cmd } returned error code { $returncode }.
packaging-error-subprocess-output = Output of the command follows:
packaging-error-traceback = Traceback:
packaging-error-aur-subject = Error retrieving AUR package
packaging-error-aur = Failed to retrieve AUR package!
packaging-error-timeout-subject = Timeout when packaging %s
packaging-error-unknown-subject = Unknown error when packaging %s
packaging-error-unknown = An unknown error happened!
packaging-log = Packaging log:

lilac-yaml-loadding-error = Failed to load lilac.yaml for %s

package-in-official-group = Packages is added to official groups: { $groups }
package-replacing-official-package = Package is replacing official packages: { $packages }
package-conflicts-with-official-repos = %s conflicts with official repos
package-older-subject = Built package %s has an older version than the one in repo
package-older-body = Package { $pkg } built as version { $built_version }, but there is a version { $repo_version } in repo already.
