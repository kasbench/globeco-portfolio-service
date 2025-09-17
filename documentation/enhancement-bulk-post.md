Add a new service that that allows a posting of up to 100 portfolios.  The path should be POST /api/v2/portfolios.  Whereas POST /api/v1/portfolios takes a single portfolio, this will take a list of portfolios.  To keep it simple, the portfolios will all be accepted or all rejected by submitting to the database as a single batch.  This will be used by a client that will deal with the fallout.  The response object should be a list of portfolios.

More specifically, the v1 api takes a PortfolioPostDTO and v2 will take [PortfolioPostDTO].  v1 returns a PortfolioResponseDTO and v2 returns a [PortfolioResponseDTO].  It can return the same ValidatonError DTO for errors, or a new one if that is easier.  Since this a new name, it does not have to maintain backward compatibility.

If the database insert fails on a recoverable error, please retry up to three times with exponential backoff.

I will do all the integration testing in Kubernetes.  You do not need to prepare testing scripts.  I already have everything I need.  I am prepared to do all the integration testing.