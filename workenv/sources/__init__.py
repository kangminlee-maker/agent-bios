"""Sources (C01): the homes, revisions and checkouts a work environment is composed from.

The entries this package serves: `source_home_register` (`homes`), `source_revision_commit` and
`source_revision_admit` (`revisions`), `reference_resolve` (`reading`), and `repository_bind` and
`source_observe` (`checkouts`). Publishing a revision is not served yet.
"""
from workenv.sources.checkouts import repository_bind, source_observe
from workenv.sources.homes import source_home_register
from workenv.sources.reading import reference_resolve
from workenv.sources.revisions import source_revision_admit, source_revision_commit

__all__ = ["reference_resolve", "repository_bind", "source_home_register", "source_observe",
           "source_revision_admit", "source_revision_commit"]
