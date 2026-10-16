

class CaseStatus:
    NEW           = "new"           # just inserted, nothing done yet
    UPLOADING     = "uploading"     # files being uploaded
    PROCESSING    = "processing"    # OCR / extraction running
    COMPLETED     = "completed"     # all done
    FAILED        = "failed"        # something went wrong
    UPDATED       = "updated"       # existing case that got new data
    INELIGIBLE    = "ineligible"    # failed pre-processing eligibility check
