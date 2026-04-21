#include <algorithm>
#include <cmath>
#include <ctime>
#include <iomanip>
#include <iostream>
#include <set>
#include <sstream>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>

using json = nlohmann::json;

struct CartItem {
    std::string sku_id;
    std::string name;
    double price = 0.0;
    int quantity = 0;
    double weight = 0.0;
    bool is_special = false;
    int stock = 0;
};

struct Coupon {
    std::string id;
    std::string type;  // "discount", "full_reduction", "fixed_price", "shipping"
    double value = 0.0;
    double min_purchase = 0.0;
    bool applicable_to_special = false;
    bool expired = false;
};

struct CheckoutData {
    std::string region;
    std::vector<CartItem> items;
    std::vector<Coupon> coupons;
};

struct CheckoutResult {
    std::string status;
    double final_payable = 0.0;

    CheckoutResult(const std::string& s, double a) : status(s), final_payable(a) {}
};

static double round2(double v) {
    return std::round(v * 100.0) / 100.0;
}

static bool is_remote_region(const std::string& region) {
    return region == "Xinjiang" || region == "Tibet" || region == "新疆" || region == "西藏";
}

static bool validate_and_check_stock(const CheckoutData& req, json& err) {
    for (const auto& item : req.items) {
        if (item.quantity <= 0) {
            err = {"status", "FAIL"};
            return false;
        }
        if (item.price < 0.0 || item.weight < 0.0 || item.stock < 0) {
            err = {"status", "FAIL"};
            return false;
        }
        if (item.quantity > item.stock) {
            err = {"status", "FAIL"};
            return false;
        }
    }
    return true;
}

static double calc_shipping_fee(const std::string& region, double total_weight, double discounted_items_total) {
    const bool remote = is_remote_region(region);
    const double first_weight_fee = remote ? 15.0 : 6.0;
    const double continue_weight_fee = remote ? 10.0 : 2.0;

    if (total_weight <= 0.0) {
        return 0.0;
    }

    const int weight_units = static_cast<int>(std::ceil(total_weight));
    double shipping = first_weight_fee;
    if (weight_units > 1) {
        shipping += (weight_units - 1) * continue_weight_fee;
    }

    if (!remote && discounted_items_total >= 99.0) {
        shipping = 0.0;
    }
    return round2(shipping);
}

static CheckoutData parse_request(const json& req_json) {
    CheckoutData req;
    const auto& data = req_json.at("data");
    req.region = data.value("region", "");

    for (const auto& x : data.at("items")) {
        CartItem i;
        i.sku_id = x.value("sku_id", "");
        i.name = x.value("name", "");
        i.price = x.value("price", 0.0);
        i.quantity = x.value("quantity", 0);
        i.weight = x.value("weight", 0.0);
        i.is_special = x.value("is_special", false);
        i.stock = x.value("stock", 0);
        req.items.push_back(i);
    }

    for (const auto& x : data.value("coupons", json::array())) {
        Coupon c;
        c.id = x.value("id", "");
        c.type = x.value("type", "");
        c.value = x.value("value", 0.0);
        c.min_purchase = x.value("min_purchase", 0.0);
        c.applicable_to_special = x.value("applicable_to_special", false);
        c.expired = x.value("expired", false);
        req.coupons.push_back(c);
    }
    return req;
}

static CheckoutResult checkout_buggy(const json& req_json) {
    if (!req_json.contains("action") || req_json.at("action") != "checkout" || !req_json.contains("data")) {
        return CheckoutResult{"FAIL", 0.0};
    }

    CheckoutData req = parse_request(req_json);
    json err;
    if (!validate_and_check_stock(req, err)) {
        return CheckoutResult{"FAIL", 0.0};
    }

    double total_original_price = 0.0;
    double total_weight = 0.0;
    double normal_items_subtotal = 0.0;
    double special_items_subtotal = 0.0;

    for (const auto& item : req.items) {
        const double line_total = round2(item.price * item.quantity);
        total_original_price += line_total;
        total_weight += item.weight * item.quantity;
        if (item.is_special) {
            special_items_subtotal += line_total;
        } else {
            normal_items_subtotal += line_total;
        }
    }

    total_original_price = round2(total_original_price);
    normal_items_subtotal = round2(normal_items_subtotal);
    special_items_subtotal = round2(special_items_subtotal);

    double coupon_savings = 0.0;
    std::set<std::string> used_coupon_types;
    double current_items_total = total_original_price;
    bool has_shipping_coupon = false;
    double shipping_coupon_value = 0.0;

    for (const auto& c : req.coupons) {
        if (c.expired) {
            continue;
        }
        if (used_coupon_types.find(c.type) != used_coupon_types.end()) {
            continue;
        }
        if (current_items_total < c.min_purchase) {
            continue;
        }

        if (c.type == "discount") {
            double base = c.applicable_to_special ? current_items_total : normal_items_subtotal;
            double discount_amount = round2(base * (1.0 - c.value));
            coupon_savings += discount_amount;
            current_items_total = round2(current_items_total - discount_amount);
        } else if (c.type == "full_reduction") {
            double reduction = std::min(current_items_total, c.value);
            reduction = round2(reduction);
            coupon_savings += reduction;
            current_items_total = round2(current_items_total - reduction);
        } else if (c.type == "fixed_price") {
            double fixed_target = std::max(0.0, c.value);
            double reduction = std::max(0.0, current_items_total - fixed_target);
            reduction = round2(reduction);
            coupon_savings += reduction;
            current_items_total = round2(current_items_total - reduction);
        } else if (c.type == "shipping") {
            has_shipping_coupon = true;
            shipping_coupon_value = std::max(shipping_coupon_value, c.value);
        }
        used_coupon_types.insert(c.type);
    }

    const double shipping_before_coupon = calc_shipping_fee(req.region, total_weight, current_items_total);
    double shipping_discount = 0.0;
    if (has_shipping_coupon) {
        shipping_discount = round2(std::min(shipping_before_coupon, shipping_coupon_value));
    }
    const double shipping_fee = round2(shipping_before_coupon - shipping_discount);
    const double final_payable = round2(current_items_total + shipping_fee);

    return CheckoutResult{"SUCCESS", final_payable};
}

extern "C" const char* checkout_from_json_buggy(const char* request_json_cstr) {
    static std::string output;
    try {
        const json req = json::parse(request_json_cstr == nullptr ? "{}" : request_json_cstr);
        CheckoutResult result = checkout_buggy(req);
        json response;
        response["status"] = result.status;
        response["final_payable"] = result.final_payable;
        output = response.dump();
    } catch (const std::exception& e) {
        json err;
        err["status"] = "FAIL";
        output = err.dump();
    }
    return output.c_str();
}

int main() {
    CheckoutData req;
    int item_count = 0;
    int coupon_count = 0;

    if (!(std::cin >> req.region >> item_count)) {
        return 0;
    }

    req.items.reserve(std::max(0, item_count));
    for (int i = 0; i < item_count; ++i) {
        CartItem item;
        std::cin >> item.sku_id >> item.name >> item.price >> item.quantity >> item.weight >> item.is_special >> item.stock;
        req.items.push_back(item);
    }

    if (!(std::cin >> coupon_count)) {
        coupon_count = 0;
    }

    req.coupons.reserve(std::max(0, coupon_count));
    for (int i = 0; i < coupon_count; ++i) {
        Coupon coupon;
        std::cin >> coupon.id >> coupon.type >> coupon.value >> coupon.min_purchase >> coupon.applicable_to_special >> coupon.expired;
        req.coupons.push_back(coupon);
    }

    json req_json;
    req_json["action"] = "checkout";
    json data_json;
    data_json["region"] = req.region;
    json items_json = json::array();
    for (const auto& item : req.items) {
        json item_json;
        item_json["sku_id"] = item.sku_id;
        item_json["name"] = item.name;
        item_json["price"] = item.price;
        item_json["quantity"] = item.quantity;
        item_json["weight"] = item.weight;
        item_json["is_special"] = item.is_special;
        item_json["stock"] = item.stock;
        items_json.push_back(item_json);
    }
    data_json["items"] = items_json;
    json coupons_json = json::array();
    for (const auto& coupon : req.coupons) {
        json coupon_json;
        coupon_json["id"] = coupon.id;
        coupon_json["type"] = coupon.type;
        coupon_json["value"] = coupon.value;
        coupon_json["min_purchase"] = coupon.min_purchase;
        coupon_json["applicable_to_special"] = coupon.applicable_to_special;
        coupon_json["expired"] = coupon.expired;
        coupons_json.push_back(coupon_json);
    }
    data_json["coupons"] = coupons_json;
    req_json["data"] = data_json;

    CheckoutResult result = checkout_buggy(req_json);
    if (result.status == "SUCCESS") {
        std::cout << "status=SUCCESS final_payable=" << result.final_payable << std::endl;
    } else {
        std::cout << "status=FAIL message=Invalid request" << std::endl;
    }
    return 0;
}