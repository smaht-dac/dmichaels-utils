from copy import deepcopy
from typing import Any, Callable, List, Optional, Tuple, Union


def merge_elasticsearch_aggregation_results(target: dict, source: dict, copy: bool = False) -> Optional[dict]:

    def get_aggregation_key(aggregation: dict, aggregation_key: Optional[str] = None) -> Optional[str]:
        if isinstance(aggregation, dict) and isinstance(aggregation.get("buckets"), list):
            if isinstance(field_name := aggregation.get("meta", {}).get("field_name"), str) and field_name:
                if isinstance(aggregation_key, str) and aggregation_key:
                    if field_name != aggregation_key:
                        return None
                return field_name
        return None

    def get_nested_aggregation(aggregation: dict) -> Optional[dict]:
        if isinstance(aggregation, dict):
            for key in aggregation:
                if get_aggregation_key(aggregation[key], key):
                    return aggregation[key]
        return None

    def get_aggregation_bucket_value(aggregation_bucket: dict) -> Optional[Any]:
        if isinstance(aggregation_bucket, dict):
            return aggregation_bucket.get("key_as_string", aggregation_bucket.get("key"))
        return None

    def get_aggregation_bucket_doc_count(aggregation_bucket: dict) -> Optional[int]:
        if isinstance(aggregation_bucket, dict):
            if isinstance(doc_count := aggregation_bucket.get("doc_count"), int):
                return doc_count
        return None

    def get_aggregation_buckets_doc_count(aggregation: dict):
        buckets_doc_count = 0
        if get_aggregation_key(aggregation):
            for aggregation_bucket in aggregation["buckets"]:
                if (doc_count := get_aggregation_bucket_doc_count(aggregation_bucket)) is not None:
                    buckets_doc_count += doc_count
        return buckets_doc_count

    def find_aggregation_bucket(aggregation: dict, value: str) -> Optional[dict]:
        if get_aggregation_key(aggregation):
            for aggregation_bucket in aggregation["buckets"]:
                if get_aggregation_bucket_value(aggregation_bucket) == value:
                    return aggregation_bucket
        return None

    def merge_results(target: dict, source: dict) -> Tuple[Optional[dict], Optional[int]]:
        merged_item_count = 0
        if not ((aggregation_key := get_aggregation_key(source)) and (get_aggregation_key(target) == aggregation_key)):
            return None, None
        for source_bucket in source["buckets"]:
            if (((source_bucket_value := get_aggregation_bucket_value(source_bucket)) is None) or
                ((source_bucket_item_count := get_aggregation_bucket_doc_count(source_bucket)) is None)):  # noqa
                continue
            if (target_bucket := find_aggregation_bucket(target, source_bucket_value)):
                if source_nested_aggregation := get_nested_aggregation(source_bucket):
                    if target_nested_aggregation := get_nested_aggregation(target_bucket):
                        merged_item_count, _ = merge_results(target_nested_aggregation, source_nested_aggregation)
                        if merged_item_count is None:
                            if source_nested_aggregation_key := get_aggregation_key(source_nested_aggregation):
                                target_bucket[source_nested_aggregation_key] = \
                                    source_bucket[source_nested_aggregation_key]
                                target_bucket["doc_count"] += \
                                    get_aggregation_buckets_doc_count(source_bucket[source_nested_aggregation_key])
                        elif merged_item_count > 0:
                            target_bucket["doc_count"] += merged_item_count
                elif get_aggregation_bucket_value(target_bucket) is not None:
                    if get_aggregation_bucket_doc_count(target_bucket) is not None:
                        target_bucket["doc_count"] += source_bucket_item_count
                        merged_item_count += source_bucket_item_count
            else:
                target["buckets"].append(source_bucket)
                if isinstance(target.get("doc_count"), int):
                    target["doc_count"] += source_bucket_item_count
                else:
                    target["doc_count"] = source_bucket_item_count
        return merged_item_count, target

    if copy is True:
        target = deepcopy(target)
    return merge_results(target, source)[1]


def normalize_elasticsearch_aggregation_results(
        aggregation: dict,
        sort: Union[bool, str, Callable, List[Union[bool, str, Callable]]] = False,
        additional_properties: Optional[dict] = None,
        remove_empty_items: bool = True) -> dict:

    def get_aggregation_key(aggregation: dict, aggregation_key: Optional[str] = None) -> Optional[str]:
        # TODO: same as in merge_elasticsearch_aggregation_results function
        if isinstance(aggregation, dict) and isinstance(aggregation.get("buckets"), list):
            if isinstance(field_name := aggregation.get("meta", {}).get("field_name"), str) and field_name:
                if isinstance(aggregation_key, str) and aggregation_key:
                    if field_name != aggregation_key:
                        return None
                return field_name
        return None

    def get_aggregation_bucket_value(aggregation_bucket: dict) -> Optional[Any]:
        # TODO: same as in merge_elasticsearch_aggregation_results function
        if isinstance(aggregation_bucket, dict):
            return aggregation_bucket.get("key_as_string", aggregation_bucket.get("key"))
        return None

    def get_aggregation_bucket_doc_count(aggregation_bucket: dict) -> Optional[int]:
        # TODO: same as in merge_elasticsearch_aggregation_results function
        if isinstance(aggregation_bucket, dict):
            if isinstance(doc_count := aggregation_bucket.get("doc_count"), int):
                return doc_count
        return None

    def get_nested_aggregations(data: dict) -> List[dict]:
        results = []
        if isinstance(data, dict):
            for key in data:
                if get_aggregation_key(data[key]) and data[key]["buckets"]:
                    results.append(data[key])
            if not results:
                if ((isinstance(data.get("buckets"), list) and data["buckets"]) or
                    (isinstance(data.get("key"), str) and isinstance(data.get("doc_count"), int))):  # noqa
                    results.append(data)
        return results

    def find_group_item(group_items: List[dict], value: Any) -> Optional[dict]:
        if isinstance(group_items, list):
            for group_item in group_items:
                if isinstance(group_item, dict) and (value == group_item.get("value")):
                    return group_item
        return None

    def normalize_results(aggregation: dict,
                          key: Optional[str] = None, value: Optional[str] = None,
                          additional_properties: Optional[dict] = None) -> dict:

        nonlocal remove_empty_items

        if not (aggregation_key := get_aggregation_key(aggregation)):
            return {}

        group_items = [] ; item_count = 0  # noqa
        for bucket in aggregation["buckets"]:
            if (((bucket_value := get_aggregation_bucket_value(bucket)) is None) or
                ((bucket_item_count := get_aggregation_bucket_doc_count(bucket)) is None)):  # noqa
                continue
            item_count += bucket_item_count
            if nested_aggregations := get_nested_aggregations(bucket):
                for nested_aggregation in nested_aggregations:
                    if normalized_aggregation := normalize_results(nested_aggregation, aggregation_key, bucket_value):
                        if group_item := find_group_item(group_items, bucket_value):
                            for normalized_aggregation_item in normalized_aggregation["items"]:
                                group_item["items"].append(normalized_aggregation_item)
                                group_item["count"] += normalized_aggregation_item["count"]
                        else:
                            group_item = normalized_aggregation
                            group_items.append(group_item)
                    else:
                        if (remove_empty_items is False) or (bucket_item_count > 0):
                            group_item = {"name": aggregation_key, "value": bucket_value, "count": bucket_item_count}
                            group_items.append(group_item)

        if (remove_empty_items is not False) and (not group_items):
            return {}
        results = {"name": key, "value": value, "count": item_count, "items": group_items}

        if isinstance(additional_properties, dict) and additional_properties:
            results = {**additional_properties, **results}

        if key is None:
            del results["name"]
            if value is None:
                del results["value"]

        return results

    def sort_results(data: dict) -> None:

        nonlocal sort

        def sort_items(items: List[dict], sort: Union[bool, str, Callable]) -> None:
            sort_function_default = lambda item: (-item.get("count", 0), item.get("value", ""))  # noqa
            if (sort is True) or (isinstance(sort, str) and (sort.strip().lower() == "default")):
                items.sort(key=sort_function_default)
            elif isinstance(sort, str) and (sort := sort.strip().lower()):
                if sort.startswith("-"):
                    sort_reverse = True
                    sort = sort[1:]
                else:
                    sort_reverse = False
                if (sort in ["default"]):
                    items.sort(key=sort_function_default, reverse=sort_reverse)
                elif (sort in ["key", "value"]):
                    items.sort(key=lambda item: item.get("value", ""), reverse=sort_reverse)
            elif callable(sort):
                items.sort(key=lambda item: sort(item))

        def sort_results_nested(data: dict, level: int = 0) -> None:
            nonlocal sort
            if isinstance(sort, list) and sort:
                if level < len(sort):
                    sort_level = sort[level]
                else:
                    sort_level = sort[len(sort) - 1]
            else:
                sort_level = sort
            if isinstance(data, dict) and isinstance(items := data.get("items"), list):
                sort_items(items, sort=sort_level)
                for item in items:
                    sort_results_nested(item, level=level + 1)

        sort_results_nested(data)

    results = normalize_results(aggregation, additional_properties=additional_properties)
    if sort:
        sort_results(results)
    return results


def normalize_elasticsearch_aggregation_results_legacy(data: dict, prefix_grouping_value: bool = True) -> dict:

    def get_nested_aggregations(data: dict) -> List[dict]:
        results = []
        if isinstance(data, dict):
            for key in data:
                if isinstance(data[key], dict) and isinstance(data[key].get("buckets"), list):
                    results.append(data[key])
            if (not results) and data.get("buckets", list):
                results.append(data)
        return results

    def normalize(aggregation: dict) -> None:
        nonlocal prefix_grouping_value
        if not (isinstance(aggregation, dict) and isinstance(buckets := aggregation.get("buckets"), list)):
            return
        group_items = {}
        item_count = 0
        for bucket in buckets:
            if (key := bucket.get("key_as_string", bucket.get("key"))) in ["No value", "null", "None"]:
                key = None
            if (prefix_grouping_value is not False) and isinstance(key, str) and key:
                if (field_name := aggregation.get("meta", {}).get("field_name")):
                    key = f"{field_name}:{key}"
            doc_count = bucket["doc_count"]
            item_count += doc_count
            if nested_aggregations := get_nested_aggregations(bucket):
                for nested_aggregation in nested_aggregations:
                    if normalized_aggregation := normalize(nested_aggregation):
                        if group_items.get(key):
                            group_items[key]["group_items"] = {**group_items[key]["group_items"],
                                                               **normalized_aggregation["group_items"]}
                            group_items[key]["item_count"] += normalized_aggregation["item_count"]
                            group_items[key]["group_count"] += normalized_aggregation["group_count"]
                        else:
                            group_items[key] = normalized_aggregation
                    else:
                        group_items[key] = doc_count

        return {
            "item_count": item_count,
            "group_count": len(group_items),
            "group_items": group_items,
        }

    if not isinstance(data, dict):
        return {}

    normalized_aggregations = {}
    if items_with_buckets_list_property := get_nested_aggregations(data):
        for item_with_buckets_list_property in items_with_buckets_list_property:
            if normalized_aggregation := normalize(item_with_buckets_list_property):
                if normalized_aggregations:
                    # Here just for completeness; in practice no multiple groupings at top-level.
                    normalized_aggregations["group_items"] = {**normalized_aggregations["group_items"],
                                                              **normalized_aggregation["group_items"]}
                else:
                    normalized_aggregations = normalized_aggregation
    return normalized_aggregations
