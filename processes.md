* lilac
  * local workerman thread (collect rusage)
    * systemd-run lilac2.worker (handle SIGINT)
      * build cmd
  * remote workerman thread (collect rusage)
    * systemd-run lilac2.remote.worker (handle SIGINT)
      * ssh host lilac2.remote.runner (collect rusage)
        * systemd-run lilac2.worker (handle SIGINT)
          * build cmd
