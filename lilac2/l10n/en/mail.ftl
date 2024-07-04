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
