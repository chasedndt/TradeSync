//! Versioned contracts shared by the future Rust real-time edge and alert router.
//!
//! This crate deliberately contains data validation only. It grants no approval,
//! trading, wallet, notification-delivery, or canonical-knowledge authority.

use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

pub const ALERT_EVENT_V1: &str = "alert_event_v1";

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum AlertSeverity {
    Info,
    Warning,
    Critical,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum AlertEnvironment {
    Paper,
    Testnet,
    Live,
    System,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum DataClassification {
    Public,
    Internal,
    Restricted,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct AlertEventV1 {
    pub schema_version: String,
    pub event_id: String,
    pub project: String,
    pub source: String,
    pub category: String,
    pub severity: AlertSeverity,
    pub environment: AlertEnvironment,
    pub title: String,
    pub body: String,
    pub created_at_ms: i64,
    pub dedupe_key: String,
    pub data_classification: DataClassification,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub symbol: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub timeframe: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub expires_at_ms: Option<i64>,
    #[serde(default)]
    pub requires_ack: bool,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub evidence_refs: Vec<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub deep_link: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub correlation_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub causation_id: Option<String>,
    #[serde(default, skip_serializing_if = "BTreeMap::is_empty")]
    pub attributes: BTreeMap<String, String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ContractError {
    UnsupportedSchemaVersion,
    EmptyField(&'static str),
    TitleTooLong,
    BodyTooLong,
    InvalidTimestamp,
    AlreadyExpired,
    TooManyEvidenceRefs,
    TooManyAttributes,
}

impl AlertEventV1 {
    pub fn validate(&self, now_ms: i64) -> Result<(), ContractError> {
        if self.schema_version != ALERT_EVENT_V1 {
            return Err(ContractError::UnsupportedSchemaVersion);
        }

        for (name, value) in [
            ("event_id", self.event_id.as_str()),
            ("project", self.project.as_str()),
            ("source", self.source.as_str()),
            ("category", self.category.as_str()),
            ("title", self.title.as_str()),
            ("body", self.body.as_str()),
            ("dedupe_key", self.dedupe_key.as_str()),
        ] {
            if value.trim().is_empty() {
                return Err(ContractError::EmptyField(name));
            }
        }

        if self.title.chars().count() > 120 {
            return Err(ContractError::TitleTooLong);
        }
        if self.body.chars().count() > 1_000 {
            return Err(ContractError::BodyTooLong);
        }
        if self.created_at_ms <= 0 {
            return Err(ContractError::InvalidTimestamp);
        }
        if self.expires_at_ms.is_some_and(|expiry| expiry <= now_ms) {
            return Err(ContractError::AlreadyExpired);
        }
        if self.evidence_refs.len() > 32 {
            return Err(ContractError::TooManyEvidenceRefs);
        }
        if self.attributes.len() > 32 {
            return Err(ContractError::TooManyAttributes);
        }

        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn valid_alert() -> AlertEventV1 {
        AlertEventV1 {
            schema_version: ALERT_EVENT_V1.to_owned(),
            event_id: "evt_01".to_owned(),
            project: "tradesync".to_owned(),
            source: "regime-engine".to_owned(),
            category: "market.regime_transition".to_owned(),
            severity: AlertSeverity::Warning,
            environment: AlertEnvironment::Paper,
            title: "BTC regime changed".to_owned(),
            body: "BTC moved from range to trend; paper review only.".to_owned(),
            created_at_ms: 1_800_000_000_000,
            dedupe_key: "btc:1h:trend".to_owned(),
            data_classification: DataClassification::Internal,
            symbol: Some("BTC".to_owned()),
            timeframe: Some("1h".to_owned()),
            expires_at_ms: Some(1_800_003_600_000),
            requires_ack: false,
            evidence_refs: vec!["market_event:evt_00".to_owned()],
            deep_link: Some("/market/BTC".to_owned()),
            correlation_id: None,
            causation_id: Some("evt_00".to_owned()),
            attributes: BTreeMap::new(),
        }
    }

    #[test]
    fn accepts_a_valid_paper_alert() {
        assert_eq!(valid_alert().validate(1_800_000_000_001), Ok(()));
    }

    #[test]
    fn rejects_unknown_versions() {
        let mut alert = valid_alert();
        alert.schema_version = "alert_event_v2".to_owned();
        assert_eq!(
            alert.validate(1_800_000_000_001),
            Err(ContractError::UnsupportedSchemaVersion)
        );
    }

    #[test]
    fn rejects_expired_alerts() {
        let mut alert = valid_alert();
        alert.expires_at_ms = Some(1_799_999_999_999);
        assert_eq!(
            alert.validate(1_800_000_000_001),
            Err(ContractError::AlreadyExpired)
        );
    }

    #[test]
    fn json_round_trip_preserves_authority_fields() {
        let alert = valid_alert();
        let encoded = serde_json::to_string(&alert).expect("serialize alert");
        let decoded: AlertEventV1 = serde_json::from_str(&encoded).expect("deserialize alert");
        assert_eq!(decoded.environment, AlertEnvironment::Paper);
        assert_eq!(decoded.data_classification, DataClassification::Internal);
        assert_eq!(decoded, alert);
    }
}
