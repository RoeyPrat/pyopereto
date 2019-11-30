# Change Log
All notable changes to this project will be documented in this file.

## [v1.0.78](https://github.com/opereto/pyopereto/releases/tag/1.0.78)
2019-11-30

### Added
* Add a notification on new versions of PyOpereto
* Add service deployment progress notification (percent of upload)
* Add command to list/delete all services of a given version

### Changed/fixed
* Opereto local mode enhancements
  * Allow to run local mode on sandbox deployments
  * Stop local mode parent flow process in case process does not exist due to data cleanup/reindexing
* Improve REST connection timeout handling (retry)
