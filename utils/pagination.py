"""
Utils — Pagination
===================
Standardises paginated list responses to the envelope format:

    {
        "data": [ ... ],
        "meta": {
            "pagination": {
                "page":        1,
                "page_size":   20,
                "total_count": 148,
                "total_pages": 8
            }
        },
        "errors": []
    }
"""

from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class StandardResultsPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100
    page_query_param = "page"

    def get_paginated_response(self, data) -> Response:
        return Response(
            {
                "data": data,
                "meta": {
                    "pagination": {
                        "page": self.page.number,
                        "page_size": self.page.paginator.per_page,
                        "total_count": self.page.paginator.count,
                        "total_pages": self.page.paginator.num_pages,
                    }
                },
                "errors": [],
            }
        )

    def get_paginated_response_schema(self, schema: dict) -> dict:
        """OpenAPI schema for drf-spectacular."""
        return {
            "type": "object",
            "properties": {
                "data": schema,
                "meta": {
                    "type": "object",
                    "properties": {
                        "pagination": {
                            "type": "object",
                            "properties": {
                                "page": {"type": "integer"},
                                "page_size": {"type": "integer"},
                                "total_count": {"type": "integer"},
                                "total_pages": {"type": "integer"},
                            },
                        }
                    },
                },
                "errors": {"type": "array", "items": {}},
            },
        }
