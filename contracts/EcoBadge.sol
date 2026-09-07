// SPDX-License-Identifier: MIT
pragma solidity ^0.4.25;

/**
 * @title EcoBadge 生态勋章与骑行券（ERC1155）
 * @dev 利用 ID 区分勋章（ID:1）和骑行券（ID:2），支持批量管理与同类多份。
 *
 *      发行权模型（对应后端 ASSET_FORMS：badge / voucher = ERC1155 · 同类多份）：
 *        - owner（创世部署方 = 联盟秘书处 0xadmin）：维护发行白名单，可为旧内置类型代签；
 *        - issuers（各业务节点组织钱包）：只能发行自己名下类型的勋章 / 骑行券
 *          （骑行券的履约义务人是共享单车节点 0xbike，所以 mint FROM 必须是它）；
 *        - 居民地址无 mint 权（只能 safeTransferFrom 流转自己持有的份数）。
 */
contract EcoBadge {
    // ID:1 = 生态勋章, ID:2 = 骑行券
    uint256 public constant BADGE_ID = 1;
    uint256 public constant VOUCHER_ID = 2;

    address public owner;                        // 联盟创世账户
    mapping(address => bool) public issuers;     // 发行权白名单

    mapping(uint256 => mapping(address => uint256)) public balances;
    mapping(address => mapping(address => bool)) public isApprovedForAll;
    mapping(uint256 => string) public tokenURI;

    event TransferSingle(address indexed operator, address indexed from, address indexed to, uint256 id, uint256 value);
    event TransferBatch(address indexed operator, address indexed from, address indexed to, uint256[] ids, uint256[] values);
    event ApprovalForAll(address indexed owner, address indexed operator, bool approved);
    event BadgeIssued(uint256 indexed id, address indexed to, uint256 value);
    event IssuerUpdated(address indexed issuer, bool allowed);

    modifier onlyOwner() {
        require(msg.sender == owner, "EB: not owner");
        _;
    }

    modifier onlyIssuer() {
        require(msg.sender == owner || issuers[msg.sender], "EB: not issuer");
        _;
    }

    constructor() public {
        owner = msg.sender;
        issuers[msg.sender] = true;
    }

    function addIssuer(address _issuer) public onlyOwner {
        require(_issuer != address(0), "EB: issuer is zero");
        issuers[_issuer] = true;
        emit IssuerUpdated(_issuer, true);
    }

    function removeIssuer(address _issuer) public onlyOwner {
        require(_issuer != address(0), "EB: issuer is zero");
        require(_issuer != owner, "EB: cannot remove owner");
        issuers[_issuer] = false;
        emit IssuerUpdated(_issuer, false);
    }

    function mint(address _to, uint256 _id, uint256 _value, string _uri) public onlyIssuer {
        require(_to != address(0), "EB: mint to zero");
        require(_value > 0, "EB: mint zero");
        balances[_id][_to] += _value;
        if (bytes(_uri).length > 0) {
            tokenURI[_id] = _uri;
        }
        emit TransferSingle(msg.sender, address(0), _to, _id, _value);
        emit BadgeIssued(_id, _to, _value);
    }

    function mintBatch(address _to, uint256[] _ids, uint256[] _values) public onlyIssuer {
        require(_to != address(0), "EB: mint to zero");
        require(_ids.length == _values.length, "EB: length mismatch");
        for (uint256 i = 0; i < _ids.length; i++) {
            balances[_ids[i]][_to] += _values[i];
        }
        emit TransferBatch(msg.sender, address(0), _to, _ids, _values);
    }

    function safeTransferFrom(address _from, address _to, uint256 _id, uint256 _value) public {
        require(_to != address(0), "EB: transfer to zero");
        require(_from == msg.sender || isApprovedForAll[_from][msg.sender], "EB: not approved");
        require(balances[_id][_from] >= _value, "EB: insufficient balance");
        balances[_id][_from] -= _value;
        balances[_id][_to] += _value;
        emit TransferSingle(msg.sender, _from, _to, _id, _value);
    }

    function setApprovalForAll(address _operator, bool _approved) public {
        isApprovedForAll[msg.sender][_operator] = _approved;
        emit ApprovalForAll(msg.sender, _operator, _approved);
    }
}
