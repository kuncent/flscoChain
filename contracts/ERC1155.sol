// SPDX-License-Identifier: MIT
pragma solidity ^0.4.25;

/**
 * @title ERC1155 多代币实训合约
 * @dev 单合约管理多种代币类型（同质化 + 非同质化）。
 */
contract ERC1155 {
    mapping(uint256 => mapping(address => uint256)) public balances;
    mapping(address => mapping(address => bool)) public isApprovedForAll;
    mapping(uint256 => string) public tokenURI;

    event TransferSingle(address indexed operator, address indexed from, address indexed to, uint256 id, uint256 value);
    event TransferBatch(address indexed operator, address indexed from, address indexed to, uint256[] ids, uint256[] values);
    event ApprovalForAll(address indexed owner, address indexed operator, bool approved);
    event URI(string value, uint256 indexed id);

    function mint(address _to, uint256 _id, uint256 _value, string _uri) public {
        require(_to != address(0), "ERC1155: mint to zero");
        balances[_id][_to] += _value;
        if (bytes(_uri).length > 0) {
            tokenURI[_id] = _uri;
            emit URI(_uri, _id);
        }
        emit TransferSingle(msg.sender, address(0), _to, _id, _value);
    }

    function mintBatch(address _to, uint256[] _ids, uint256[] _values) public {
        require(_to != address(0), "ERC1155: mint to zero");
        require(_ids.length == _values.length, "ERC1155: length mismatch");
        for (uint256 i = 0; i < _ids.length; i++) {
            balances[_ids[i]][_to] += _values[i];
        }
        emit TransferBatch(msg.sender, address(0), _to, _ids, _values);
    }

    function safeTransferFrom(address _from, address _to, uint256 _id, uint256 _value) public {
        require(_to != address(0), "ERC1155: transfer to zero");
        require(_from == msg.sender || isApprovedForAll[_from][msg.sender], "ERC1155: not approved");
        require(balances[_id][_from] >= _value, "ERC1155: insufficient balance");
        balances[_id][_from] -= _value;
        balances[_id][_to] += _value;
        emit TransferSingle(msg.sender, _from, _to, _id, _value);
    }

    function setApprovalForAll(address _operator, bool _approved) public {
        isApprovedForAll[msg.sender][_operator] = _approved;
        emit ApprovalForAll(msg.sender, _operator, _approved);
    }
}
