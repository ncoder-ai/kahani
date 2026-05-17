//
//  NativePinLockPlugin.swift
//  Kahani — App PIN lock backed by iOS Keychain
//
//  Stores a PBKDF2-HMAC-SHA256 hash of the user's PIN in Keychain Services
//  along with a random salt. The plaintext PIN never touches disk — only
//  the derived hash. The hash is verified by re-deriving from the input PIN
//  + stored salt and constant-time comparing.
//
//  Why Keychain (not UserDefaults/Preferences):
//  - Survives app reinstall by default (kSecAttrAccessibleAfterFirstUnlock).
//  - Encrypted at rest via the device passcode-derived key.
//  - Not readable from a jailbroken backup the same way plist files are.
//
//  Failed-attempts counter is stored alongside the hash. Reaching the
//  cap (5) returns `locked: true` from verifyPin so the JS side can
//  force a logout flow. resetFailedAttempts is intentionally NOT exposed
//  to JS — clearing only happens on successful verifyPin or clearPin.
//
//  Threading: Keychain ops are blocking syscalls. We dispatch off the
//  main thread so the WKWebView UI doesn't stall on PBKDF2 (100k iter
//  takes ~50ms on modern A-series).
//

import Capacitor
import CommonCrypto
import Foundation
import Security

@objc(NativePinLockPlugin)
public class NativePinLockPlugin: CAPPlugin, CAPBridgedPlugin {
    public let identifier = "NativePinLockPlugin"
    public let jsName = "NativePinLock"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "setPin", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "verifyPin", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "hasPin", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "clearPin", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "getFailedAttempts", returnType: CAPPluginReturnPromise),
    ]

    // MARK: - Configuration

    private let service = "com.makemysaga.app.applock"
    private let pinAccount = "pin.hash"
    private let attemptsAccount = "pin.failed_attempts"
    private let pbkdf2Iterations: UInt32 = 100_000
    private let saltLength = 16
    private let hashLength = 32
    private let maxFailedAttempts = 5

    private let workQueue = DispatchQueue(label: "com.makemysaga.app.pinlock", qos: .userInitiated)

    // MARK: - Plugin methods

    @objc func setPin(_ call: CAPPluginCall) {
        guard let pin = call.getString("pin"), !pin.isEmpty else {
            call.reject("Missing or empty 'pin'")
            return
        }
        workQueue.async { [weak self] in
            guard let self = self else { return }
            do {
                let salt = try self.randomBytes(length: self.saltLength)
                let hash = try self.derive(pin: pin, salt: salt)
                let payload = self.encodePayload(salt: salt, hash: hash)
                try self.keychainSet(account: self.pinAccount, data: payload)
                // Clear any stale failure counter so a fresh PIN starts at 0.
                try self.keychainDelete(account: self.attemptsAccount)
                call.resolve(["success": true])
            } catch {
                call.reject("setPin failed: \(error.localizedDescription)")
            }
        }
    }

    @objc func verifyPin(_ call: CAPPluginCall) {
        guard let pin = call.getString("pin"), !pin.isEmpty else {
            call.reject("Missing or empty 'pin'")
            return
        }
        workQueue.async { [weak self] in
            guard let self = self else { return }
            do {
                guard let stored = try self.keychainGet(account: self.pinAccount) else {
                    call.reject("No PIN set")
                    return
                }
                guard let (salt, expected) = self.decodePayload(stored) else {
                    call.reject("Stored PIN is corrupt")
                    return
                }
                let current = try self.derive(pin: pin, salt: salt)
                let valid = self.constantTimeEqual(current, expected)

                let attempts: Int
                if valid {
                    // Clear counter on success.
                    try self.keychainDelete(account: self.attemptsAccount)
                    attempts = 0
                } else {
                    let next = try self.readAttempts() + 1
                    try self.writeAttempts(next)
                    attempts = next
                }
                let remaining = max(0, self.maxFailedAttempts - attempts)
                let locked = !valid && attempts >= self.maxFailedAttempts
                call.resolve([
                    "valid": valid,
                    "attemptsRemaining": remaining,
                    "locked": locked,
                ])
            } catch {
                call.reject("verifyPin failed: \(error.localizedDescription)")
            }
        }
    }

    @objc func hasPin(_ call: CAPPluginCall) {
        workQueue.async { [weak self] in
            guard let self = self else { return }
            do {
                let data = try self.keychainGet(account: self.pinAccount)
                call.resolve(["enabled": data != nil])
            } catch {
                call.reject("hasPin failed: \(error.localizedDescription)")
            }
        }
    }

    @objc func clearPin(_ call: CAPPluginCall) {
        workQueue.async { [weak self] in
            guard let self = self else { return }
            do {
                try self.keychainDelete(account: self.pinAccount)
                try self.keychainDelete(account: self.attemptsAccount)
                call.resolve(["success": true])
            } catch {
                call.reject("clearPin failed: \(error.localizedDescription)")
            }
        }
    }

    @objc func getFailedAttempts(_ call: CAPPluginCall) {
        workQueue.async { [weak self] in
            guard let self = self else { return }
            do {
                let count = try self.readAttempts()
                call.resolve([
                    "count": count,
                    "remaining": max(0, self.maxFailedAttempts - count),
                    "locked": count >= self.maxFailedAttempts,
                ])
            } catch {
                call.reject("getFailedAttempts failed: \(error.localizedDescription)")
            }
        }
    }

    // MARK: - Crypto

    private func randomBytes(length: Int) throws -> Data {
        var bytes = [UInt8](repeating: 0, count: length)
        let status = SecRandomCopyBytes(kSecRandomDefault, length, &bytes)
        guard status == errSecSuccess else {
            throw PinLockError.cryptoFailed("SecRandomCopyBytes \(status)")
        }
        return Data(bytes)
    }

    private func derive(pin: String, salt: Data) throws -> Data {
        guard let pinBytes = pin.data(using: .utf8) else {
            throw PinLockError.cryptoFailed("PIN UTF-8 encoding failed")
        }
        // Capture all lengths up front. Reading `derived.count` inside the
        // `derived.withUnsafeMutableBytes` closure would be an overlapping
        // access — the closure already holds an exclusive mutable borrow,
        // and Swift's memory-exclusivity rule rejects a concurrent read.
        let derivedLen = hashLength
        let saltLen = salt.count
        let pinLen = pinBytes.count
        let iterations = pbkdf2Iterations
        var derived = Data(count: derivedLen)
        let status = derived.withUnsafeMutableBytes { (derivedPtr: UnsafeMutableRawBufferPointer) -> Int32 in
            salt.withUnsafeBytes { (saltPtr: UnsafeRawBufferPointer) -> Int32 in
                pinBytes.withUnsafeBytes { (pinPtr: UnsafeRawBufferPointer) -> Int32 in
                    CCKeyDerivationPBKDF(
                        CCPBKDFAlgorithm(kCCPBKDF2),
                        pinPtr.bindMemory(to: Int8.self).baseAddress,
                        pinLen,
                        saltPtr.bindMemory(to: UInt8.self).baseAddress,
                        saltLen,
                        CCPseudoRandomAlgorithm(kCCPRFHmacAlgSHA256),
                        iterations,
                        derivedPtr.bindMemory(to: UInt8.self).baseAddress,
                        derivedLen
                    )
                }
            }
        }
        guard status == kCCSuccess else {
            throw PinLockError.cryptoFailed("PBKDF2 status \(status)")
        }
        return derived
    }

    private func constantTimeEqual(_ a: Data, _ b: Data) -> Bool {
        guard a.count == b.count else { return false }
        var diff: UInt8 = 0
        for i in 0..<a.count {
            diff |= a[i] ^ b[i]
        }
        return diff == 0
    }

    // MARK: - Payload encoding

    // Payload layout: 1 byte version + 1 byte saltLen + salt + hash.
    // Fixed-size after the salt-length byte (hash length is implicit from
    // the SHA-256 output size, validated on decode).

    private func encodePayload(salt: Data, hash: Data) -> Data {
        var out = Data()
        out.append(1) // version
        out.append(UInt8(salt.count))
        out.append(salt)
        out.append(hash)
        return out
    }

    private func decodePayload(_ data: Data) -> (salt: Data, hash: Data)? {
        guard data.count >= 2 else { return nil }
        let version = data[0]
        guard version == 1 else { return nil }
        let saltLen = Int(data[1])
        let expectedTotal = 2 + saltLen + hashLength
        guard data.count == expectedTotal else { return nil }
        let salt = data.subdata(in: 2..<(2 + saltLen))
        let hash = data.subdata(in: (2 + saltLen)..<expectedTotal)
        return (salt, hash)
    }

    // MARK: - Failed-attempts counter

    private func readAttempts() throws -> Int {
        guard let data = try keychainGet(account: attemptsAccount) else { return 0 }
        guard let str = String(data: data, encoding: .utf8), let n = Int(str) else { return 0 }
        return n
    }

    private func writeAttempts(_ value: Int) throws {
        guard let data = String(value).data(using: .utf8) else {
            throw PinLockError.cryptoFailed("attempts encoding failed")
        }
        try keychainSet(account: attemptsAccount, data: data)
    }

    // MARK: - Keychain wrappers

    private func keychainBaseQuery(account: String) -> [String: Any] {
        return [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
    }

    private func keychainSet(account: String, data: Data) throws {
        // Try update first; if not found, add. Accessibility is only set
        // on insert — SecItemUpdate inherits the attribute that was on
        // the existing row.
        let update: [String: Any] = [
            kSecValueData as String: data,
        ]
        let updateStatus = SecItemUpdate(
            keychainBaseQuery(account: account) as CFDictionary,
            update as CFDictionary
        )
        if updateStatus == errSecSuccess { return }
        if updateStatus != errSecItemNotFound {
            throw PinLockError.keychainFailed("update status \(updateStatus)")
        }
        var insert = keychainBaseQuery(account: account)
        insert[kSecValueData as String] = data
        insert[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        let addStatus = SecItemAdd(insert as CFDictionary, nil)
        guard addStatus == errSecSuccess else {
            throw PinLockError.keychainFailed("add status \(addStatus)")
        }
    }

    private func keychainGet(account: String) throws -> Data? {
        var query = keychainBaseQuery(account: account)
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne
        var item: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &item)
        if status == errSecItemNotFound { return nil }
        guard status == errSecSuccess else {
            throw PinLockError.keychainFailed("get status \(status)")
        }
        return item as? Data
    }

    private func keychainDelete(account: String) throws {
        let status = SecItemDelete(keychainBaseQuery(account: account) as CFDictionary)
        if status == errSecSuccess || status == errSecItemNotFound { return }
        throw PinLockError.keychainFailed("delete status \(status)")
    }

    private enum PinLockError: Error, LocalizedError {
        case cryptoFailed(String)
        case keychainFailed(String)

        var errorDescription: String? {
            switch self {
            case .cryptoFailed(let msg): return "crypto: \(msg)"
            case .keychainFailed(let msg): return "keychain: \(msg)"
            }
        }
    }
}
