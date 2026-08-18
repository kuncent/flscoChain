// SPDX-License-Identifier: MIT
pragma solidity ^0.4.25;

/**
 * @title EcoBadge 生态勋章与骑行券（ERC1155）
 * @dev 利用 ID 区分勋章（ID:1）和骑行券（ID:2），支持批量管理。
 *      联盟链各节点可发放勋章，共享单车节点可发放骑行券。
 */
contract EcoBadge {
    // ID:1 = 生态勋章, ID:2 = 骑行券
    uint256 public constant BADGE_ID = 1;
    uint256 public constant VOUCHER_ID = 2;

    mapping(uint256 => mapping(address => uint256)) public balances;
    mapping(address => mapping(address => bool)) public isApprovedForAll;
    mapping(uint256 => string) public tokenURI;

    event TransferSingle(address indexed operator, address indexed from, address indexed to, uint256 id, uint256 value);
    event TransferBatch(address indexed operator, address indexed from, address indexed to, uint256[] ids, uint256[] values);
    event ApprovalForAll(address indexed owner, address indexed operator, bool approved);
    event BadgeIssued(uint256 indexed id, address indexed to, uint256 value);

    function mint(address _to, uint256 _id, uint256 _value, string _uri) public {
        require(_to != address(0), "EB: mint to zero");
        require(_value > 0, "EB: mint zero");
        balances[_id][_to] += _value;
        if (bytes(_uri).length > 0) {
            tokenURI[_id] = _uri;
        }
        emit TransferSingle(msg.sender, address(0), _to, _id, _value);
        emit BadgeIssued(_id, _to, _value);
    }

    function mintBatch(address _to, uint256[] _ids, uint256[] _values) public {
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
